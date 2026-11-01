FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt requirements-docker.lock ./
RUN pip install --no-cache-dir -r requirements.txt gunicorn -c requirements-docker.lock

COPY app.py compress.py ./
COPY static ./static

RUN useradd --create-home appuser
USER appuser

EXPOSE 8765

# shortcut: jobs live in process memory; use one worker/replica until jobs are shared.
CMD ["gunicorn", "--bind", "0.0.0.0:8765", "--workers", "1", "--threads", "1", "--timeout", "600", "--access-logfile", "-", "--error-logfile", "-", "app:app"]
