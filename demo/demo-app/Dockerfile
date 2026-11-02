FROM python:latest

WORKDIR /app
COPY . /app

RUN pip install --no-cache-dir flask && chmod -R 777 /app

USER root

CMD ["python", "app.py"]
