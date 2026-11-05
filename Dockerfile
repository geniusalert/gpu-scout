FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bot.py integrations.py research.py supplier_data.py webhook_server.py ./
ENV DATABASE_PATH=/data/scout.db
RUN mkdir /data
CMD ["python", "webhook_server.py"]
