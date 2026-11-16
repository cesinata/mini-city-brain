# Build from the repository root: docker build -f services/worker/Dockerfile -t mcb-worker .
FROM python:3.13.5-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements/worker.txt requirements/constraints.txt /tmp/requirements/
RUN pip install -r /tmp/requirements/worker.txt -c /tmp/requirements/constraints.txt \
    && rm -rf /tmp/requirements

COPY services/__init__.py services/__init__.py
COPY services/common services/common
COPY services/worker services/worker

RUN useradd --system --uid 10001 --no-create-home app
USER 10001

EXPOSE 9101

# The worker serves Prometheus metrics on 9101; a failed scrape means the loop has stopped.
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:9101/metrics', timeout=2).status == 200 else 1)"

CMD ["python", "-m", "services.worker.main"]
