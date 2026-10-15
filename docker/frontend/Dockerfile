FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=5004 \
    USER_SERVICE_URL=http://user-service:5001 \
    PRODUCT_SERVICE_URL=http://product-service:5002 \
    ORDER_SERVICE_URL=http://order-service:5003

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY frontend/ ./frontend/

RUN chown -R 10001:10001 /app

USER 10001:10001

EXPOSE 5004

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5004/health', timeout=3)" || exit 1

CMD ["uvicorn", "frontend.app:app", "--host", "0.0.0.0", "--port", "5004"]
