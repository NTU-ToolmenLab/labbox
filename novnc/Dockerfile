FROM python:3.7-slim
RUN pip3 --no-cache-dir install numpy
RUN mkdir -p /app/novnc
RUN touch /app/db.sqlite

WORKDIR /app/novnc
EXPOSE 6080
# "python3 websockify/websockify.py :6080 --token-plugin dbToken --token-source /app/db.sqlite --web build"
CMD ["python3", "websockify/websockify.py", ":6080", "--token-plugin", "dbToken", "--token-source", "/app/db.sqlite", "--web", "build"]
