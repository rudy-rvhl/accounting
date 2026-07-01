# QCRE — containerized web app. Runs the FastAPI/HTMX UI on the demo company by default.
# Build:  docker build -t qcre .
# Run:    docker run -p 8000:8000 qcre     → open http://localhost:8000
# Deploy: any container host (Render, Railway, Fly.io, Cloud Run) that reads $PORT.
FROM python:3.11-slim

# System libraries: WeasyPrint (PDF export) + Tesseract/Poppler (OCR for scanned PDFs).
RUN apt-get update && apt-get install -y --no-install-recommends \
      libpango-1.0-0 libpangoft2-1.0-0 libpangocairo-1.0-0 \
      libcairo2 libgdk-pixbuf-2.0-0 libffi8 libfontconfig1 fonts-dejavu-core \
      tesseract-ocr tesseract-ocr-fra poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY qcre ./qcre
RUN pip install --no-cache-dir ".[pdf,ocr]"

# Optional: mount/point QCRE_DB at a saved company database; defaults to the demo company.
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn qcre.web.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
