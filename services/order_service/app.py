"""Order service: create and retrieve shoe orders using the user and product services."""

import os
import sqlite3
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = Path(os.environ.get("ORDER_DB_PATH", ROOT / "data" / "orders.db"))
USER_SERVICE_URL = os.environ.get("USER_SERVICE_URL", "http://127.0.0.1:5001").rstrip("/")
PRODUCT_SERVICE_URL = os.environ.get("PRODUCT_SERVICE_URL", "http://127.0.0.1:5002").rstrip("/")
HTTP_TIMEOUT = float(os.environ.get("HTTP_TIMEOUT", "5"))


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message


class OrderItemIn(BaseModel):
    product_id: int = Field(ge=1)
    quantity: int = Field(ge=1)


class OrderIn(BaseModel):
    user_id: int = Field(ge=1)
    items: list[OrderItemIn] = Field(min_length=1)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def cents_to_money(cents: int) -> float:
    return cents / 100


def price_to_cents(price: float) -> int:
    return int(Decimal(str(price)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) * 100)


@contextmanager
def get_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                user_name TEXT NOT NULL,
                user_email TEXT NOT NULL,
                status TEXT NOT NULL,
                total_cents INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL REFERENCES orders(id),
                product_id INTEGER NOT NULL,
                product_name TEXT NOT NULL,
                brand TEXT NOT NULL DEFAULT '',
                size TEXT NOT NULL DEFAULT '',
                color TEXT NOT NULL DEFAULT '',
                quantity INTEGER NOT NULL,
                unit_price_cents INTEGER NOT NULL
            )
            """
        )
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(order_items)")}
        for name in ("brand", "size", "color"):
            if name not in columns:
                conn.execute(f"ALTER TABLE order_items ADD COLUMN {name} TEXT NOT NULL DEFAULT ''")


def order_to_dict(conn: sqlite3.Connection, row: sqlite3.Row) -> dict:
    items = conn.execute(
        "SELECT * FROM order_items WHERE order_id = ? ORDER BY id",
        (row["id"],),
    ).fetchall()
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "user_name": row["user_name"],
        "user_email": row["user_email"],
        "status": row["status"],
        "total": cents_to_money(row["total_cents"]),
        "created_at": row["created_at"],
        "items": [
            {
                "product_id": item["product_id"],
                "product_name": item["product_name"],
                "brand": item["brand"],
                "size": item["size"],
                "color": item["color"],
                "quantity": item["quantity"],
                "unit_price": cents_to_money(item["unit_price_cents"]),
            }
            for item in items
        ],
    }


def service_get(url: str):
    try:
        response = httpx.get(url, timeout=HTTP_TIMEOUT)
    except httpx.HTTPError:
        raise ApiError(503, "dependent service is unavailable") from None
    if response.status_code == 404:
        return None
    if response.is_error:
        raise ApiError(502, "dependent service returned an error")
    return response.json()


def adjust_stock(product_id: int, delta: int):
    try:
        response = httpx.patch(
            f"{PRODUCT_SERVICE_URL}/products/{product_id}/stock",
            json={"delta": delta},
            timeout=HTTP_TIMEOUT,
        )
    except httpx.HTTPError:
        raise ApiError(503, "product service is unavailable") from None
    if response.status_code == 409:
        body = response.json() if response.content else {}
        raise ApiError(409, body.get("error", "insufficient stock"))
    if response.status_code == 404:
        raise ApiError(404, "product not found")
    if response.is_error:
        raise ApiError(502, "product service returned an error")
    return response.json()


def release_stock(reservations: list[tuple[int, int]]) -> None:
    for product_id, quantity in reversed(reservations):
        adjust_stock(product_id, quantity)


def validation_message(exc: RequestValidationError) -> str:
    err = exc.errors()[0]
    loc = [str(part) for part in err["loc"] if part != "body"]
    field = loc[-1] if loc else "request"
    return f"{field} {err['msg']}"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Order service", lifespan=lifespan)


@app.exception_handler(ApiError)
def handle_api_error(_request, exc: ApiError):
    return JSONResponse(status_code=exc.status, content={"error": exc.message})


@app.exception_handler(RequestValidationError)
def handle_validation(_request, exc: RequestValidationError):
    return JSONResponse(status_code=400, content={"error": validation_message(exc)})


@app.get("/")
def index():
    return {
        "service": "order",
        "framework": "fastapi",
        "endpoints": ["GET /health", "GET /orders", "POST /orders", "GET /orders/{id}", "POST /orders/{id}/cancel"],
    }


@app.get("/health")
def health():
    return {"status": "ok", "service": "order"}


@app.get("/orders")
def list_orders(user_id: int | None = None):
    query = "SELECT * FROM orders"
    params: tuple = ()
    if user_id is not None:
        query += " WHERE user_id = ?"
        params = (user_id,)
    query += " ORDER BY id"
    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
        return [order_to_dict(conn, row) for row in rows]


@app.get("/orders/{order_id}")
def get_order(order_id: int):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        if row is None:
            raise ApiError(404, "order not found")
        return order_to_dict(conn, row)


@app.post("/orders", status_code=201)
def create_order(payload: OrderIn):
    requested: dict[int, int] = {}
    for item in payload.items:
        requested[item.product_id] = requested.get(item.product_id, 0) + item.quantity

    user = service_get(f"{USER_SERVICE_URL}/users/{payload.user_id}")
    if user is None:
        raise ApiError(404, "user not found")

    lines = []
    for product_id, quantity in requested.items():
        product = service_get(f"{PRODUCT_SERVICE_URL}/products/{product_id}")
        if product is None:
            raise ApiError(404, f"product {product_id} not found")
        if product["stock"] < quantity:
            raise ApiError(409, f"insufficient stock for product {product_id}")
        lines.append(
            {
                "product_id": product_id,
                "product_name": product["name"],
                "brand": product.get("brand", ""),
                "size": product.get("size", ""),
                "color": product.get("color", ""),
                "quantity": quantity,
                "unit_price_cents": price_to_cents(product["price"]),
            }
        )

    reserved: list[tuple[int, int]] = []
    try:
        for line in lines:
            adjust_stock(line["product_id"], -line["quantity"])
            reserved.append((line["product_id"], line["quantity"]))
    except ApiError:
        release_stock(reserved)
        raise

    total_cents = sum(line["unit_price_cents"] * line["quantity"] for line in lines)
    try:
        with get_db() as conn:
            cur = conn.execute(
                """
                INSERT INTO orders (user_id, user_name, user_email, status, total_cents, created_at)
                VALUES (?, ?, ?, 'created', ?, ?)
                """,
                (user["id"], user["name"], user["email"], total_cents, utc_now()),
            )
            order_id = cur.lastrowid
            conn.executemany(
                """
                INSERT INTO order_items
                    (order_id, product_id, product_name, brand, size, color, quantity, unit_price_cents)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        order_id,
                        line["product_id"],
                        line["product_name"],
                        line["brand"],
                        line["size"],
                        line["color"],
                        line["quantity"],
                        line["unit_price_cents"],
                    )
                    for line in lines
                ],
            )
            row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
            return order_to_dict(conn, row)
    except sqlite3.Error:
        release_stock(reserved)
        raise ApiError(500, "could not save the order") from None


@app.post("/orders/{order_id}/cancel")
def cancel_order(order_id: int):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        if row is None:
            raise ApiError(404, "order not found")
        if row["status"] == "cancelled":
            raise ApiError(409, "order is already cancelled")
        items = conn.execute(
            "SELECT product_id, quantity FROM order_items WHERE order_id = ?",
            (order_id,),
        ).fetchall()

    restored: list[tuple[int, int]] = []
    try:
        for item in items:
            adjust_stock(item["product_id"], item["quantity"])
            restored.append((item["product_id"], -item["quantity"]))
    except ApiError:
        release_stock(restored)
        raise

    with get_db() as conn:
        conn.execute("UPDATE orders SET status = 'cancelled' WHERE id = ?", (order_id,))
        row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        return order_to_dict(conn, row)


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", "5003")))
