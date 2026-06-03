FROM python:3.11-slim

WORKDIR /app

# 依存
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# danjer_gaia パッケージ
COPY danjer_gaia /app/danjer_gaia

# Cloud Run 標準 PORT
ENV PORT=8080
EXPOSE 8080

# Min Instance=1 と組み合わせて、 keep_alive を起動時から回す
CMD ["python3", "-m", "danjer_gaia.live.cloud_run_main"]
