FROM python:3.11-slim

# WeasyPrint + PyMuPDF native deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 \
    libffi-dev libjpeg-dev libopenjp2-7 shared-mime-info curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
# CPU-only torch build: the default PyPI wheel bundles CUDA libraries meant
# for GPU servers, which balloons both image size and runtime memory on a
# CPU-only host — this alone was exceeding the 512MB free-tier limit just to
# load sentence-transformers. Installed first so the later requirements.txt
# install sees torch's dependency already satisfied and doesn't replace it.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt

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
