"""Product service: multi-brand shoe catalog and stock."""

import os
import sqlite3
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = Path(os.environ.get("PRODUCT_DB_PATH", ROOT / "data" / "products.db"))
CATEGORIES = {"running", "lifestyle", "court", "trail"}

SHOES = [
    ("Nike", "Pegasus 41", "running", "10", "Black", "Daily trainer with a responsive foam midsole", 14000, 18),
    ("Nike", "Dunk Low", "lifestyle", "9", "White/Grey", "Leather low-top with a classic court shape", 11500, 12),
    ("Adidas", "Samba OG", "lifestyle", "8", "Black/White", "Suede and leather terrace shoe", 10000, 20),
    ("Adidas", "Ultraboost 5", "running", "11", "Core Black", "Knit upper with energy-returning cushioning", 19000, 9),
    ("Puma", "Suede Classic", "lifestyle", "9", "Navy", "Soft suede street shoe", 7500, 22),
    ("Puma", "Deviate Nitro", "running", "10", "Fire Red", "Lightweight racing trainer", 16000, 8),
    ("New Balance", "550", "lifestyle", "8.5", "White/Green", "Retro basketball silhouette", 12000, 14),
    ("New Balance", "Fresh Foam 1080", "running", "10.5", "Grey", "Plush daily mileage shoe", 16500, 11),
    ("Converse", "Chuck 70", "lifestyle", "7", "Black", "High-top canvas with extra cushioning", 9000, 16),
    ("ASICS", "Gel-Kayano 31", "running", "9.5", "Blue", "Stability shoe for long runs", 16500, 10),
    ("Vans", "Old Skool", "lifestyle", "8", "Black/White", "Suede and canvas skate shoe", 7500, 24),
    ("On", "Cloudmonster", "running", "10", "White", "Max-cushion road shoe", 18000, 7),
    ("Hoka", "Clifton 9", "running", "9", "Sky Blue", "Light cushioned daily trainer", 14500, 13),
    ("Reebok", "Club C 85", "lifestyle", "8", "Chalk", "Clean leather tennis shoe", 8500, 15),
]


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message


def cents_from_price(value: float) -> int:
    try:
        amount = Decimal(str(value))
        quantized = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        raise ValueError("must be a non-negative amount with at most two decimal places") from None
    if amount < 0 or quantized != amount:
        raise ValueError("must be a non-negative amount with at most two decimal places")
    return int(quantized * 100)


class ShoeIn(BaseModel):
    brand: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=160)
    category: str
    size: str = Field(min_length=1, max_length=16)
    color: str = Field(min_length=1, max_length=40)
    description: str = Field(default="", max_length=1000)
    price: float = Field(ge=0)
    stock: int = Field(ge=0)

    @field_validator("brand", "name", "size", "color")
    @classmethod
    def clean_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must be a non-empty string")
        return cleaned

    @field_validator("description")
    @classmethod
    def clean_description(cls, value: str) -> str:
        return value.strip()

    @field_validator("category")
    @classmethod
    def clean_category(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if cleaned not in CATEGORIES:
            raise ValueError("must be running, lifestyle, court, or trail")
        return cleaned

    @field_validator("price")
    @classmethod
    def clean_price(cls, value: float) -> float:
        cents_from_price(value)
        return value


class StockAdjust(BaseModel):
    delta: int

    @field_validator("delta")
    @classmethod
    def nonzero(cls, value: int) -> int:
        if value == 0:
            raise ValueError("must be a non-zero integer")
        return value


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@contextmanager
def get_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            brand TEXT NOT NULL,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            size TEXT NOT NULL,
            color TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            price_cents INTEGER NOT NULL CHECK (price_cents >= 0),
            stock INTEGER NOT NULL CHECK (stock >= 0),
            created_at TEXT NOT NULL
        )
        """
    )


def init_db() -> None:
    with get_db() as conn:
        existing = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'products'"
        ).fetchone()
        if existing is not None:
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(products)")}
            if "brand" not in columns:
                conn.execute("DROP TABLE products")
        create_table(conn)
        count = conn.execute("SELECT COUNT(*) AS n FROM products").fetchone()["n"]
        if count == 0:
            now = utc_now()
            conn.executemany(
                """
                INSERT INTO products
                    (brand, name, category, size, color, description, price_cents, stock, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [(*shoe, now) for shoe in SHOES],
            )


def product_to_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "brand": row["brand"],
        "name": row["name"],
        "category": row["category"],
        "size": row["size"],
        "color": row["color"],
        "description": row["description"],
        "price": row["price_cents"] / 100,
        "stock": row["stock"],
        "created_at": row["created_at"],
    }


def validation_message(exc: RequestValidationError) -> str:
    err = exc.errors()[0]
    loc = [str(part) for part in err["loc"] if part != "body"]
    field = loc[-1] if loc else "request"
    return f"{field} {err['msg']}"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Product service", lifespan=lifespan)


@app.exception_handler(ApiError)
def handle_api_error(_request, exc: ApiError):
    return JSONResponse(status_code=exc.status, content={"error": exc.message})


@app.exception_handler(RequestValidationError)
def handle_validation(_request, exc: RequestValidationError):
    return JSONResponse(status_code=400, content={"error": validation_message(exc)})


@app.get("/")
def index():
    return {
        "service": "product",
        "framework": "fastapi",
        "endpoints": [
            "GET /health",
            "GET /products",
            "GET /brands",
            "POST /products",
            "GET /products/{id}",
            "PUT /products/{id}",
            "PATCH /products/{id}/stock",
            "DELETE /products/{id}",
        ],
    }


@app.get("/health")
def health():
    return {"status": "ok", "service": "product"}


@app.get("/brands")
def list_brands():
    with get_db() as conn:
        rows = conn.execute("SELECT DISTINCT brand FROM products ORDER BY brand").fetchall()
    return [row["brand"] for row in rows]


@app.get("/products")
def list_products(brand: str | None = None, category: str | None = None):
    query = "SELECT * FROM products WHERE 1 = 1"
    params: list[str] = []
    if brand:
        query += " AND lower(brand) = lower(?)"
        params.append(brand.strip())
    if category:
        query += " AND category = ?"
        params.append(category.strip().lower())
    query += " ORDER BY brand, name"
    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
    return [product_to_dict(row) for row in rows]


@app.post("/products", status_code=201)
def create_product(payload: ShoeIn):
    with get_db() as conn:
        cur = conn.execute(
            """
            INSERT INTO products
                (brand, name, category, size, color, description, price_cents, stock, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.brand,
                payload.name,
                payload.category,
                payload.size,
                payload.color,
                payload.description,
                cents_from_price(payload.price),
                payload.stock,
                utc_now(),
            ),
        )
        row = conn.execute("SELECT * FROM products WHERE id = ?", (cur.lastrowid,)).fetchone()
    return product_to_dict(row)


@app.get("/products/{product_id}")
def get_product(product_id: int):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    if row is None:
        raise ApiError(404, "product not found")
    return product_to_dict(row)


@app.put("/products/{product_id}")
def update_product(product_id: int, payload: ShoeIn):
    with get_db() as conn:
        cur = conn.execute(
            """
            UPDATE products
            SET brand = ?, name = ?, category = ?, size = ?, color = ?, description = ?, price_cents = ?, stock = ?
            WHERE id = ?
            """,
            (
                payload.brand,
                payload.name,
                payload.category,
                payload.size,
                payload.color,
                payload.description,
                cents_from_price(payload.price),
                payload.stock,
                product_id,
            ),
        )
        if cur.rowcount == 0:
            raise ApiError(404, "product not found")
        row = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    return product_to_dict(row)


@app.patch("/products/{product_id}/stock")
def adjust_stock(product_id: int, payload: StockAdjust):
    with get_db() as conn:
        cur = conn.execute(
            """
            UPDATE products
            SET stock = stock + ?
            WHERE id = ? AND stock + ? >= 0
            """,
            (payload.delta, product_id, payload.delta),
        )
        if cur.rowcount == 0:
            exists = conn.execute("SELECT id FROM products WHERE id = ?", (product_id,)).fetchone()
            if exists is None:
                raise ApiError(404, "product not found")
            raise ApiError(409, "insufficient stock")
        row = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    return product_to_dict(row)


@app.delete("/products/{product_id}", status_code=204)
def delete_product(product_id: int):
    with get_db() as conn:
        cur = conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
    if cur.rowcount == 0:
        raise ApiError(404, "product not found")
    return Response(status_code=204)


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", "5002")))
