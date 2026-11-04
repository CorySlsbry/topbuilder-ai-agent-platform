# Top Builder AI API — Cloud Run-ready image.
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install the package (and its runtime deps) from the project metadata.
COPY pyproject.toml ./
COPY app ./app
COPY migrations ./migrations
COPY scripts ./scripts
RUN pip install . \
 && adduser --disabled-password --gecos "" appuser \
 && chown -R appuser /app

COPY scripts/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER appuser
EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
