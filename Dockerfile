FROM python:3.11-slim

# Instala FFmpeg e dependências de sistema
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsm6 \
    libxext6 \
    libgl1 \
    wget \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# CRÍTICO: apaga a pasta 'queue' que conflitua com o módulo Python
RUN rm -rf /app/queue

# Cria diretórios necessários
RUN mkdir -p output/videos output/images output/audio output/logs \
    assets/music assets/fonts templates job_queue

EXPOSE 7860

ENV PYTHONUNBUFFERED=1
ENV TTS_ENGINE=edge-tts
ENV SD_USE_LOCAL=false

CMD ["python", "app.py"]
