# ---- Base image (small + maintained) ----
FROM python:3.11-slim

# ---- System deps for audio (discord voice) ----
# ffmpeg: audio transcoding/streaming
# libopus0: opus codec for voice
RUN apt-get update  && apt-get install -y --no-install-recommends ffmpeg libopus0  && rm -rf /var/lib/apt/lists/*

# ---- App setup ----
WORKDIR /app

# Copy only requirements first (better cache)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the source
COPY . .

# Ensure logs stream immediately
ENV PYTHONUNBUFFERED=1

# If you run as a Web Service with HTTP healthcheck, the app may read $PORT
# (Worker 타입이면 별도 포트 노출 필요 없음)
# ENV PORT=8000

# Default entrypoint
CMD ["python", "bot_koyeb.py"]
