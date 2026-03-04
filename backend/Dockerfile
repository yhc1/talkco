FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

# Runtime dependencies for FastAPI + asyncpg backend.
RUN pip install --no-cache-dir \
    fastapi \
    uvicorn \
    python-multipart \
    pydantic-settings \
    asyncpg \
    openai

COPY backend/ /app/
COPY shared/ /shared/

EXPOSE 8000

CMD ["python", "main.py"]
