FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bot.py integrations.py research.py supplier_data.py ./
ENV DATABASE_PATH=/data/scout.db
RUN mkdir /data
CMD ["python", "bot.py"]
