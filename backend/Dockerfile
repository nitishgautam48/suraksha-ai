# syntax=docker/dockerfile:1.7
# Build context: project root (docker compose sets this).
FROM python:3.11-slim-bookworm

ARG INSTALL_VOICE=true
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    XDG_CACHE_HOME=/models/cache \
    TTS_HOME=/models/tts \
    HF_HOME=/models/huggingface \
    COQUI_TOS_AGREED=1 \
    PYTHONPATH=/app

# OCR (Tesseract + Indian language packs), audio decoding for Whisper, libsndfile for TTS output.
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-eng tesseract-ocr-hin tesseract-ocr-guj tesseract-ocr-mar \
        tesseract-ocr-tam tesseract-ocr-ben tesseract-ocr-tel tesseract-ocr-kan tesseract-ocr-mal \
        tesseract-ocr-pan tesseract-ocr-ori tesseract-ocr-asm \
        ffmpeg libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements.txt backend/requirements-voice.txt /tmp/
RUN pip install -r /tmp/requirements.txt

# Local speech models: CPU-only PyTorch keeps the image several GB smaller than the CUDA build.
RUN if [ "$INSTALL_VOICE" = "true" ]; then \
        pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu \
        && pip install -r /tmp/requirements-voice.txt ; \
    else echo "Skipping voice dependencies"; fi

RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin app \
    && mkdir -p /data/uploads /data/knowledge /models \
    && chown -R app:app /data /models

COPY --chown=app:app backend /app/backend
COPY --chown=app:app scripts /app/scripts
RUN chmod +x /app/scripts/*.sh

USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=4)"]

# docker compose runs this with `init: true` (tini) so signals reach uvicorn / celery.
CMD ["/app/scripts/start.sh"]
