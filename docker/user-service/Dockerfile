FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=5001 \
    USER_DB_PATH=/app/data/users.db

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY services/user_service/ ./services/user_service/

RUN mkdir -p /app/data \
    && chown -R 10001:10001 /app

USER 10001:10001

EXPOSE 5001

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5001/health', timeout=3)" || exit 1

CMD ["uvicorn", "services.user_service.app:app", "--host", "0.0.0.0", "--port", "5001"]