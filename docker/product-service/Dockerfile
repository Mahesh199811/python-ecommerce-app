FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=5002 \
    PRODUCT_DB_PATH=/app/data/products.db

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY services/product_service/ ./services/product_service/

RUN mkdir -p /app/data \
    && chown -R 10001:10001 /app

USER 10001:10001

EXPOSE 5002

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5002/health', timeout=3)" || exit 1

CMD ["uvicorn", "services.product_service.app:app", "--host", "0.0.0.0", "--port", "5002"]
