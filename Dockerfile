FROM node:20-alpine AS frontend-builder
WORKDIR /build
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build
FROM python:3.12-slim
WORKDIR /app
RUN sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources
RUN apt-get update && apt-get install -y ffmpeg curl git ca-certificates && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt ./backend/
RUN pip install --no-cache-dir --proxy http://10.182.67.191:8080 -r backend/requirements.txt
COPY backend/ ./backend/
COPY --from=frontend-builder /build/dist /app/backend/static
COPY backend/app/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
HEALTHCHECK CMD curl -f http://localhost:8000/api/health || exit 1
ENTRYPOINT ["/entrypoint.sh"]
