FROM python:3.9-slim

# ──────────────────────────────────────────────────────────────────────
# System dependencies
#   • can-utils / iproute2 / kmod  → SocketCAN (candump, ip link, modprobe)
#   • libvulkan1                   → Vulkan loader (NVIDIA drivers provided at runtime)
#   • python3-tk                   → tkinter (screen size detection)
#   • libsdl2-*                    → Pygame runtime
#   • libfreetype6-dev             → font rendering
#   • fontconfig / fonts-dejavu    → system fonts for Pygame font discovery
# ──────────────────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    can-utils \
    fontconfig \
    fonts-dejavu-core \
    iproute2 \
    kmod \
    libvulkan1 \
    python3-tk \
    libsdl2-dev \
    libsdl2-image-dev \
    libsdl2-mixer-dev \
    libsdl2-ttf-dev \
    libfreetype6-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies (cached layer — only rebuilt when requirements change)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire platform source
COPY . .

# Make the entrypoint executable
RUN chmod +x docker-entrypoint.sh

ENTRYPOINT ["/app/docker-entrypoint.sh"]
