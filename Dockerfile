# CodeShot API — Production Dockerfile

FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    wget curl ca-certificates fonts-liberation ffmpeg \
    libasound2 libatk-bridge2.0-0 libatk1.0-0 libcups2 libdrm2 \
    libgbm1 libgtk-3-0 libnspr4 libnss3 libx11-xcb1 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 xdg-utils \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

ENV PLAYWRIGHT_BROWSERS_PATH=/opt/pw
RUN python3 -m playwright install --with-deps chromium

COPY app/ ./app/

RUN useradd -m app && chown -R app:app /app /opt/pw
USER app

EXPOSE 8000
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

CMD ["python3", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
