FROM python:3.9-slim

# SocketCAN tools, tkinter, and fonts used by the client GUIs.
# The Pygame wheel supplies its own SDL runtime libraries.
RUN apt-get update && apt-get install -y --no-install-recommends \
    can-utils \
    fontconfig \
    fonts-dejavu-core \
    iproute2 \
    kmod \
    python3-tk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies before copying source to preserve build cache usage.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x docker-entrypoint.sh

ENTRYPOINT ["/app/docker-entrypoint.sh"]
