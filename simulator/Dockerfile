FROM python:3.12-slim

# Run as a non-root user: a container should not need root to send telemetry
RUN useradd --create-home app
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY validation.py simulate.py ./
USER app

CMD ["python", "simulate.py", "--backfill", "6"]
