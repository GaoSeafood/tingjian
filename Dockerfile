FROM node:22-alpine AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM node:22-bookworm-slim AS javascript-runtime

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates xvfb xauth patch \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app/backend
COPY --from=javascript-runtime /usr/local/bin/node /usr/local/bin/node
RUN node --version
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
# Temporary upstream Douyin fix: yt-dlp/yt-dlp#17826, head 728fe46fbaa97d6f03efcaf9e766d4db63338b8d.
COPY backend/douyin-yt-dlp.patch /tmp/douyin-yt-dlp.patch
RUN cd /usr/local/lib/python3.12/site-packages && patch -p1 < /tmp/douyin-yt-dlp.patch && rm /tmp/douyin-yt-dlp.patch
RUN python -m playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*
COPY backend/ ./
COPY --from=frontend /build/dist /app/static
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
