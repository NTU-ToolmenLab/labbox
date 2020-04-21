FROM python:3.8-slim
RUN pip3 install --no-cache-dir kubernetes flask gunicorn pyaml
RUN mkdir /app
COPY . /app
WORKDIR /app
EXPOSE 3476
CMD ["python3", "/app/api.py"]
