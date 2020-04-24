FROM python:3.8-slim
RUN pip3 install --no-cache-dir \
    flask Flask-SQLAlchemy flask-login \
    Authlib flask-admin passlib requests \
    redis celery python-dateutil \
    paramiko Flask-Testing lxml \
    gunicorn

COPY . /app
WORKDIR /app
ENV TZ Asia/Taipei
CMD ["bash", "/app/run.sh"]
