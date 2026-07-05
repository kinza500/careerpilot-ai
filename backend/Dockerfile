FROM python:3.11-slim

# WeasyPrint + PyMuPDF native deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 \
    libffi-dev libjpeg-dev libopenjp2-7 shared-mime-info curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the embedding model so first request isn't slow / networked.
RUN python -c "from sentence_transformers import SentenceTransformer; \
    SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

COPY . .

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# -w 1: a single worker on a memory-constrained free-tier instance. Each
# worker eagerly loads torch + the embedding model at startup; 2 workers
# means 2 full copies loaded simultaneously, which was exceeding the
# platform's memory limit.
CMD ["gunicorn", "app.main:app", "-k", "uvicorn.workers.UvicornWorker", \
     "-b", "0.0.0.0:8000", "-w", "1", "--timeout", "180"]
