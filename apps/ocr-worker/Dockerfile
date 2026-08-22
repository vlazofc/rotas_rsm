FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# tesseract-ocr (fallback), poppler (pdf2image) e libs do OpenCV/EasyOCR
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-por \
        poppler-utils \
        libgl1 libglib2.0-0 libgomp1 \
        libpq-dev build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["celery", "-A", "worker.celery_app", "worker", "--loglevel=info", "--concurrency=1", "-Q", "ocr"]
