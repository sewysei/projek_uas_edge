FROM python:3.11-slim-bookworm

# Install dependensi C untuk pembacaan GPIO DHT11 di Raspberry Pi
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgpiod2 \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY sensor_agent.py coordinator_agent.py ./

CMD ["python", "-u", "sensor_agent.py"]