FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot ./bot

# Tandu is arm64; python:3.11-slim is multi-arch so this works on both.
EXPOSE 8765

CMD ["python", "-m", "bot.main"]
