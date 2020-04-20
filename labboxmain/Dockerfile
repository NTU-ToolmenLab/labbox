FROM python:3.7-slim
RUN pip3 install --no-cache-dir \
    flask Flask-SQLAlchemy flask-login \
    Authlib passlib requests \
    redis celery python-dateutil \
    paramiko Flask-Testing lxml \
    gunicorn

RUN mkdir -p /app
WORKDIR /app
ENV TZ Asia/Taipei
CMD ["bash", "/app/run.sh"]
