FROM python:3.11-slim

# پلے رائٹ کے لیے ضروری سسٹم لائبریریاں انسٹال کرنا
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxcb1 \
    libxkbcommon0 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libatspi2.0-0t64 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpangoft2-1.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# صرف براؤزر انسٹال کریں، ڈیپینڈینسز اوپر apt-get سے پوری ہو چکی ہیں
RUN playwright install chromium

COPY . .

EXPOSE 8080

CMD ["python", "app.py"]
