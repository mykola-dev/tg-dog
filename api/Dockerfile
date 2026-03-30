FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    nodejs \
    npm \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-ukr \
    tesseract-ocr-rus \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g opencode-ai

COPY requirements.txt /app/requirements.txt
COPY api/requirements.txt /app/api/requirements.txt

RUN pip install --no-cache-dir -r /app/requirements.txt -r /app/api/requirements.txt

COPY . /app

EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
