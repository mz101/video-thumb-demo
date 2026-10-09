# Eigenes Dockerfile statt Nixpacks — ffmpeg wird als Systempaket gebraucht.
FROM python:3.12-slim

# ffmpeg samt ffprobe. opencv-python-headless zieht keine GUI-Bibliotheken
# nach, deshalb reicht die schlanke Basis — libgomp1 braucht es trotzdem,
# die OpenCV-Wheels sind gegen OpenMP gelinkt und python:slim bringt es nicht mit.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg libgomp1 \
 && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DATEN_PFAD=/data

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY loupe/ ./loupe/
COPY app/ ./app/

# Fällt zurück, falls kein Volume gemountet ist — dann ist die Ablage
# flüchtig und Jobs überleben kein Deploy. Siehe README.
RUN mkdir -p /data

EXPOSE 8000

# Ein Worker-Prozess. Die Job-Verarbeitung läuft in Threads darin; mehrere
# uvicorn-Worker hätten getrennte Warteschlangen und würden sich die CPU
# gegenseitig wegnehmen.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
