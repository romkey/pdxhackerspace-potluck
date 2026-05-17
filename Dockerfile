FROM python:3.12-slim

WORKDIR /app

# Install dependencies first so this layer is cached between rebuilds.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

# The SQLite database lives here; mount a volume to keep it across restarts.
ENV POTLUCK_DB=/data/potluck.db
EXPOSE 8080

# 2 workers is plenty for a potluck. --threads keeps SQLite access tidy.
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--threads", "4", "app:app"]
