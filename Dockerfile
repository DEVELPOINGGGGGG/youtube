# Use a lightweight Python Linux environment
FROM python:3.10-slim

# 1. Install system utilities and FFmpeg directly into Linux
RUN apt-get update && apt-get install -y curl gnupg lsb-release ffmpeg

# 2. Add the official Cloudflare WARP repository keys
RUN curl -fsSL https://pkg.cloudflareclient.com/pubkey.gpg | gpg --dearmor -o /usr/share/keyrings/cloudflare-warp-archive-keyring.gpg
RUN echo "deb [signed-by=/usr/share/keyrings/cloudflare-warp-archive-keyring.gpg] https://pkg.cloudflareclient.com/ $(lsb_release -cs) main" | tee /etc/apt/sources.list.d/cloudflare-client.list

# 3. Install Cloudflare WARP
RUN apt-get update && apt-get install -y cloudflare-warp

# 4. Set up the Python Application
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy your app.py and start.sh into the container
COPY . .

# Make the startup script executable
RUN chmod +x start.sh

# Expose port 5000 for web traffic
EXPOSE 5000

# Fire the startup script when the container launches
CMD ["./start.sh"]
