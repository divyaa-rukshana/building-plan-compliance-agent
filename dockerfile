FROM python:3.10-slim

WORKDIR /app

# Upgrade pip to prevent resolution and network metadata errors
RUN pip install --no-cache-dir --upgrade pip

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
ENV PYTHONPATH=/app