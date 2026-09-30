FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    SIMBA_DATA=/data \
    SIMBA_WORKSPACE=/data/workspace \
    OBSERVER_ENABLED=false \
    BROWSER_ENABLED=false \
    HOME=/data/home
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# The repo root IS the "simba" package (server.py uses relative imports),
# so copy it into /app/simba and launch it as a package.
COPY . /app/simba
# config.py sets ROOT=/app and server.py serves the web app from ROOT/pwa
RUN mv /app/simba/pwa /app/pwa
EXPOSE 8000
CMD ["sh", "-c", "mkdir -p /data/home /data/workspace && uvicorn simba.server:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
