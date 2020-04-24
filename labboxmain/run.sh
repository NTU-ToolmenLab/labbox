celery worker -A labboxmain.celery -B -D -l info -f /data/main_celery.log --pidfile=/tmp/%n.pid -s /tmp/celerybeat-schedule
gunicorn -b 0.0.0.0:5000 labboxmain:app --access-logfile /data/main_access.log -p /tmp/gunicorn.pid
