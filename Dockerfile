FROM python:3.11-slim

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

# REMOVE a pasta 'queue' ANTES de qualquer import Python
# Ela conflitua com o módulo nativo 'queue' do Python
RUN rm -rf /app/queue && \
    rm -rf /app/queue/__init__.py && \
    echo "Queue folder removed"

# Verifica que foi removida
RUN python -c "import queue; from queue import Queue; print('queue module OK')"

RUN mkdir -p output/videos output/images output/audio output/logs \
    assets/music assets/fonts templates job_queue

EXPOSE 7860

ENV PYTHONUNBUFFERED=1
ENV TTS_ENGINE=edge-tts
ENV SD_USE_LOCAL=false

CMD ["python", "app.py"]
