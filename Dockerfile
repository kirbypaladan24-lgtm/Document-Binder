FROM python:3.12-slim

WORKDIR /srv

# LibreOffice (headless) converts Word/PowerPoint uploads to PDF.
# This adds size to the image but needs zero app code changes.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libreoffice-writer libreoffice-impress \
        fonts-dejavu fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-web.txt .
RUN pip install --no-cache-dir -r requirements-web.txt

COPY web ./web
COPY src ./src

ENV PORT=8000 \
    WEB_DATA_DIR=/data \
    PYTHONUNBUFFERED=1

VOLUME /data
EXPOSE 8000

CMD ["gunicorn", "web.app:app", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "4", "--timeout", "300"]
