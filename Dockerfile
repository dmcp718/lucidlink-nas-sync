FROM debian:bookworm

LABEL maintainer="LucidLink Sync Container"
LABEL description="Container for syncing files between local storage and LucidLink filespace using parallel rsync"

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Install required packages including Python 3.11
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    rsync \
    parallel \
    fuse \
    ca-certificates \
    cron \
    procps \
    inotify-tools \
    python3 \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

# Download and install LucidLink client (new download URL format)
RUN wget -q "https://www.lucidlink.com/download/new-ll-latest/linux-deb/stable/" -O /tmp/lucidinstaller.deb \
    && apt-get update \
    && apt-get install -y /tmp/lucidinstaller.deb \
    && rm /tmp/lucidinstaller.deb \
    && rm -rf /var/lib/apt/lists/*

# Configure FUSE for container access
RUN echo "user_allow_other" >> /etc/fuse.conf

# Create directories
RUN mkdir -p /data/local /data/filespace /scripts /config /var/log/sync /cache

# Create Python virtual environment and install dependencies
COPY requirements.txt /tmp/requirements.txt
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

# Copy scripts
COPY scripts/entrypoint.sh /scripts/entrypoint.sh
COPY scripts/sync.sh /scripts/sync.sh
COPY scripts/parallel-rsync.sh /scripts/parallel-rsync.sh

# Copy web application
COPY webapp /webapp

# Make scripts executable
RUN chmod +x /scripts/*.sh

# Environment variables (override at runtime)
ENV LUCIDLINK_FILESPACE=""
ENV LUCIDLINK_USER=""
ENV LUCIDLINK_PASSWORD=""
ENV LUCIDLINK_MOUNT_POINT="/data/filespace"
ENV LOCAL_DATA_PATH="/data/local"

# Web UI environment variables
ENV WEBUI_ENABLED="true"
ENV WEBUI_PORT="8080"

# Add venv to PATH
ENV PATH="/opt/venv/bin:$PATH"

# Volume mount points
VOLUME ["/data/local", "/data/filespace", "/config", "/cache"]

# Expose web UI port
EXPOSE 8080

ENTRYPOINT ["/scripts/entrypoint.sh"]
