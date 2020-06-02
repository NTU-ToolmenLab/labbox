FROM python:3.8-slim
RUN pip3 install --no-cache-dir requests jinja2
COPY . /app/
WORKDIR /app
CMD ["python3", "/app/notify.py"]
