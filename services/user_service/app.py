"""User service: create, list, fetch, update, and delete shoppers."""

import os
import re
import sqlite3
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = Path(os.environ.get("USER_DB_PATH", ROOT / "data" / "users.db"))
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message


class UserIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=254)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must be a non-empty string")
        return cleaned

    @field_validator("email")
    @classmethod
    def clean_email(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if not EMAIL_RE.match(cleaned):
            raise ValueError("must be a valid email address")
        return cleaned


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


def init_db() -> None:
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            )
            """
        )
        count = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
        if count == 0:
            now = utc_now()
            conn.executemany(
                "INSERT INTO users (name, email, created_at) VALUES (?, ?, ?)",
                [
                    ("Ava Shah", "ava@example.com", now),
                    ("Noah Patel", "noah@example.com", now),
                ],
            )


def user_to_dict(row: sqlite3.Row) -> dict:
    return {"id": row["id"], "name": row["name"], "email": row["email"], "created_at": row["created_at"]}


def validation_message(exc: RequestValidationError) -> str:
    err = exc.errors()[0]
    loc = [str(part) for part in err["loc"] if part != "body"]
    field = loc[-1] if loc else "request"
    return f"{field} {err['msg']}"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="User service", lifespan=lifespan)


@app.exception_handler(ApiError)
def handle_api_error(_request, exc: ApiError):
    return JSONResponse(status_code=exc.status, content={"error": exc.message})


@app.exception_handler(RequestValidationError)
def handle_validation(_request, exc: RequestValidationError):
    return JSONResponse(status_code=400, content={"error": validation_message(exc)})


@app.get("/")
def index():
    return {
        "service": "user",
        "framework": "fastapi",
        "endpoints": ["GET /health", "GET /users", "POST /users", "GET /users/{id}", "PUT /users/{id}", "DELETE /users/{id}"],
    }


@app.get("/health")
def health():
    return {"status": "ok", "service": "user"}


@app.get("/users")
def list_users():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM users ORDER BY id").fetchall()
    return [user_to_dict(row) for row in rows]


@app.post("/users", status_code=201)
def create_user(payload: UserIn):
    try:
        with get_db() as conn:
            cur = conn.execute(
                "INSERT INTO users (name, email, created_at) VALUES (?, ?, ?)",
                (payload.name, payload.email, utc_now()),
            )
            row = conn.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()
    except sqlite3.IntegrityError:
        raise ApiError(409, "email already exists") from None
    return user_to_dict(row)


@app.get("/users/{user_id}")
def get_user(user_id: int):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        raise ApiError(404, "user not found")
    return user_to_dict(row)


@app.put("/users/{user_id}")
def update_user(user_id: int, payload: UserIn):
    try:
        with get_db() as conn:
            cur = conn.execute(
                "UPDATE users SET name = ?, email = ? WHERE id = ?",
                (payload.name, payload.email, user_id),
            )
            if cur.rowcount == 0:
                raise ApiError(404, "user not found")
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    except sqlite3.IntegrityError:
        raise ApiError(409, "email already exists") from None
    return user_to_dict(row)


@app.delete("/users/{user_id}", status_code=204)
def delete_user(user_id: int):
    with get_db() as conn:
        cur = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    if cur.rowcount == 0:
        raise ApiError(404, "user not found")
    return Response(status_code=204)


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", "5001")))
