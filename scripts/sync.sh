#!/bin/bash
# Main sync orchestrator script

LOG_FILE="/var/log/sync/sync.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Default values
SOURCE=""
DEST=""

case "$SYNC_DIRECTION" in
    "local-to-filespace"|"push")
        SOURCE="$LOCAL_DATA_PATH/"
        DEST="$LUCIDLINK_MOUNT_POINT/"
        log "Sync direction: Local -> Filespace"
        ;;
    "filespace-to-local"|"pull")
        SOURCE="$LUCIDLINK_MOUNT_POINT/"
        DEST="$LOCAL_DATA_PATH/"
        log "Sync direction: Filespace -> Local"
        ;;
    "bidirectional"|"both")
        log "Sync direction: Bidirectional"
        log "  Phase 1: Local -> Filespace"
        SOURCE="$LOCAL_DATA_PATH/"
        DEST="$LUCIDLINK_MOUNT_POINT/"
        /scripts/parallel-rsync.sh "$SOURCE" "$DEST"

        log "  Phase 2: Filespace -> Local"
        SOURCE="$LUCIDLINK_MOUNT_POINT/"
        DEST="$LOCAL_DATA_PATH/"
        /scripts/parallel-rsync.sh "$SOURCE" "$DEST"
        exit 0
        ;;
    *)
        log "ERROR: Invalid SYNC_DIRECTION: $SYNC_DIRECTION"
        log "Valid options: local-to-filespace, filespace-to-local, bidirectional"
        exit 1
        ;;
esac

# Run parallel rsync
/scripts/parallel-rsync.sh "$SOURCE" "$DEST"
