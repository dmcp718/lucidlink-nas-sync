#!/bin/bash
set -e

LOG_FILE="/var/log/sync/container.log"
WEBUI_PID=""

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "Starting LucidLink Sync Container"

# Check for required environment variables
if [ -z "$LUCIDLINK_FILESPACE" ]; then
    log "ERROR: LUCIDLINK_FILESPACE environment variable is required"
    exit 1
fi

if [ -z "$LUCIDLINK_USER" ]; then
    log "ERROR: LUCIDLINK_USER environment variable is required"
    exit 1
fi

if [ -z "$LUCIDLINK_PASSWORD" ]; then
    log "ERROR: LUCIDLINK_PASSWORD environment variable is required"
    exit 1
fi

# Check for /dev/fuse
if [ ! -e /dev/fuse ]; then
    log "ERROR: /dev/fuse not available. Container must be run with:"
    log "  --device /dev/fuse"
    log "  --cap-add SYS_ADMIN"
    exit 1
fi

# Ensure directories exist
mkdir -p "$LUCIDLINK_MOUNT_POINT"
mkdir -p "$LOCAL_DATA_PATH"
mkdir -p /cache
mkdir -p /config

log "Configuration:"
log "  Filespace: $LUCIDLINK_FILESPACE"
log "  User: $LUCIDLINK_USER"
log "  Mount Point: $LUCIDLINK_MOUNT_POINT"
log "  Local Data Path: $LOCAL_DATA_PATH"
log "  Web UI Port: ${WEBUI_PORT:-8080}"

# Start LucidLink daemon
log "Starting LucidLink daemon..."

# Check if daemon is already running
if pgrep -x "lucid" > /dev/null; then
    log "LucidLink daemon already running"
else
    # Start daemon in background with FUSE allow-other and cache path
    lucid daemon \
        --fs "$LUCIDLINK_FILESPACE" \
        --user "$LUCIDLINK_USER" \
        --password "$LUCIDLINK_PASSWORD" \
        --mount-point "$LUCIDLINK_MOUNT_POINT" \
        --fuse-allow-other \
        --root-path /cache &

    DAEMON_PID=$!
    log "LucidLink daemon started (PID: $DAEMON_PID)"
fi

# Wait for filespace to mount
log "Waiting for filespace to mount..."
MAX_WAIT=120
WAITED=0

# Check if LucidLink FUSE mount is active by looking at /proc/mounts
is_mounted() {
    grep -q "$LUCIDLINK_MOUNT_POINT fuse" /proc/mounts 2>/dev/null
}

while ! is_mounted && [ $WAITED -lt $MAX_WAIT ]; do
    sleep 2
    WAITED=$((WAITED + 2))
    log "  Waiting... ($WAITED/$MAX_WAIT seconds)"
done

if ! is_mounted; then
    log "ERROR: Filespace failed to mount within $MAX_WAIT seconds"
    log "Checking LucidLink status..."
    lucid status || true
    exit 1
fi

log "Filespace mounted successfully at $LUCIDLINK_MOUNT_POINT"

# Show filespace status
lucid status || true

# Start Web UI if enabled
if [ "${WEBUI_ENABLED:-true}" = "true" ]; then
    log "Starting Web UI on port ${WEBUI_PORT:-8080}..."
    uvicorn webapp.main:app \
        --host 0.0.0.0 \
        --port "${WEBUI_PORT:-8080}" \
        --log-level info \
        --access-log &
    WEBUI_PID=$!
    log "Web UI started (PID: $WEBUI_PID)"
fi

# Handle graceful shutdown
cleanup() {
    log "Received shutdown signal, cleaning up..."

    # Stop Web UI
    if [ -n "$WEBUI_PID" ] && kill -0 "$WEBUI_PID" 2>/dev/null; then
        log "Stopping Web UI..."
        kill "$WEBUI_PID" || true
        wait "$WEBUI_PID" 2>/dev/null || true
    fi

    # Stop LucidLink
    lucid exit || true

    log "Container stopped"
    exit 0
}

trap cleanup SIGTERM SIGINT

# Keep container alive - all syncing is done through Web UI jobs
log "Ready. Use Web UI to create and manage sync jobs."
if [ -n "$WEBUI_PID" ]; then
    wait $WEBUI_PID
else
    while true; do sleep 86400; done
fi
