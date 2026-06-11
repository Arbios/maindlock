FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 libcurl4 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# writable caches for the HF user; llama.cpp backend by default
ENV HOME=/tmp HF_HOME=/tmp/hf MINDLOCK_BACKEND=llamacpp PORT=7860
EXPOSE 7860
CMD ["python", "app.py"]
