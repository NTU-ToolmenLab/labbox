FROM python:3.7-slim
RUN pip3 --no-cache-dir install numpy
RUN mkdir -p /app
COPY build /app/build
COPY websockify /app/websockify

WORKDIR /app
EXPOSE 6080
# "python3 websockify/websockify.py :6080 --token-plugin dbToken --token-source /app/db.sqlite --web build"
CMD ["bash", "/app/websockify/websockify.py", ":6080", "--token-plugin", "dbToken", "--token-source", "/data/db.sqlite", "--web", "/app/build"]
