"""Shoe storefront. Serves the UI and proxies the three FastAPI services."""

import os
from contextlib import asynccontextmanager

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
USER_SERVICE_URL = os.environ.get("USER_SERVICE_URL", "http://127.0.0.1:5001").rstrip("/")
PRODUCT_SERVICE_URL = os.environ.get("PRODUCT_SERVICE_URL", "http://127.0.0.1:5002").rstrip("/")
ORDER_SERVICE_URL = os.environ.get("ORDER_SERVICE_URL", "http://127.0.0.1:5003").rstrip("/")
HTTP_TIMEOUT = float(os.environ.get("HTTP_TIMEOUT", "5"))

SERVICES = {
    "users": USER_SERVICE_URL,
    "products": PRODUCT_SERVICE_URL,
    "orders": ORDER_SERVICE_URL,
}
METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.client = httpx.AsyncClient(timeout=HTTP_TIMEOUT)
    yield
    await app.state.client.aclose()


app = FastAPI(title="Stride storefront", docs_url=None, redoc_url=None, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/health")
def health():
    return {"status": "ok", "service": "frontend", "framework": "fastapi"}


@app.get("/api/health")
async def api_health(request: Request):
    services = {}
    for name, base in SERVICES.items():
        try:
            upstream = await request.app.state.client.get(f"{base}/health")
            services[name] = upstream.is_success
        except httpx.HTTPError:
            services[name] = False
    status = "ok" if all(services.values()) else "degraded"
    return JSONResponse(
        status_code=200 if status == "ok" else 503,
        content={"status": status, "services": services},
    )


@app.api_route("/api/{service}", methods=METHODS)
@app.api_route("/api/{service}/{path:path}", methods=METHODS)
async def proxy(service: str, request: Request, path: str = ""):
    base = SERVICES.get(service)
    if base is None:
        return JSONResponse(status_code=404, content={"error": "unknown service"})

    upstream_path = f"/{service}" if not path else f"/{service}/{path}"
    headers = {}
    if request.headers.get("content-type"):
        headers["Content-Type"] = request.headers["content-type"]
    try:
        upstream = await request.app.state.client.request(
            request.method,
            f"{base}{upstream_path}",
            params=request.query_params,
            content=await request.body(),
            headers=headers,
        )
    except httpx.HTTPError:
        return JSONResponse(status_code=503, content={"error": f"{service} service is unavailable"})

    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type"),
    )


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", "5004")))
