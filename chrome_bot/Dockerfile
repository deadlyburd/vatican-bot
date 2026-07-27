FROM ubuntu:22.04

# Avoid prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Install dependencies
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    xvfb \
    x11vnc \
    fluxbox \
    unzip \
    curl \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libwayland-client0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Install Chrome
RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies for the booking agent
RUN pip3 install --no-cache-dir nodriver requests

# Create directories
RUN mkdir -p /root/chrome-profiles /root/browser-extension /root/scripts /root/logs

# Set working directory
WORKDIR /root

# Copy startup script and booking agent
COPY chrome_bot/start-chrome.sh /root/scripts/
COPY local_browser_agent.py /root/scripts/
RUN chmod +x /root/scripts/start-chrome.sh

# Expose remote debugging port
EXPOSE 9222

# Expose VNC port (optional)
EXPOSE 5900

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -f http://localhost:9222/json || exit 1

# Start script
CMD ["/root/scripts/start-chrome.sh"]
