FROM python:3.8-slim
RUN pip3 install --no-cache-dir flask docker gunicorn
COPY . /app/
WORKDIR /app
EXPOSE 3476
CMD ["python3", "/app/api.py"]
