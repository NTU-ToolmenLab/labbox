FROM nvidia/cuda:10.2-base
RUN apt update -y && \
    apt install -y python3-pip && \
    rm -rf /var/lib/apt/lists/* && \
    pip3 install --no-cache-dir psutil prometheus_client
COPY . /app/
WORKDIR /app
CMD ["python3", "/app/monitor.py"]
