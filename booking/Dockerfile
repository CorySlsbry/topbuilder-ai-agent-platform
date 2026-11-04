# Top Builder AI — custom booking service (Cloud Run).
FROM python:3.13-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY app.py book.html ./
EXPOSE 8080
# Cloud Run injects $PORT (8080). Shell form so the var expands.
CMD exec uvicorn app:app --host 0.0.0.0 --port ${PORT:-8080}
