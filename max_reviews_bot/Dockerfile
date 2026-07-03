FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/tmp/.cache/faster-whisper \
    HUGGINGFACE_HUB_CACHE=/tmp/.cache/faster-whisper \
    XDG_CACHE_HOME=/tmp/.cache

COPY max_reviews_bot/requirements.txt ./requirements.txt
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY max_reviews_bot/ ./
COPY core_logic.py ./core_logic.py

CMD ["python", "app.py"]
