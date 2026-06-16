FROM python:3.10-slim

# Install system utilities, FFmpeg, and Aria2c
RUN apt-get update && apt-get install -y curl gnupg lsb-release ffmpeg dbus aria2

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
