FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    SMK_PORT=8765 \
    SMK_NO_BROWSER=1 \
    LANG=C.UTF-8

RUN apt-get update && apt-get install -y --no-install-recommends \
      libreoffice-writer fonts-dejavu fonts-liberation \
      tzdata ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

EXPOSE 8765
CMD ["python", "server.py"]
