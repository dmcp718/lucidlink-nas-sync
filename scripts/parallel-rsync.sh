#!/bin/bash
# Parallel rsync script - uses GNU parallel to run multiple rsync jobs

set -e

SOURCE="$1"
DEST="$2"

LOG_FILE="/var/log/sync/parallel-rsync.log"
JOBS="${PARALLEL_JOBS:-4}"
RSYNC_OPTS="${RSYNC_OPTIONS:--avz --progress}"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

if [ -z "$SOURCE" ] || [ -z "$DEST" ]; then
    log "ERROR: Usage: parallel-rsync.sh <source> <dest>"
    exit 1
fi

log "Starting parallel rsync"
log "  Source: $SOURCE"
log "  Destination: $DEST"
log "  Parallel jobs: $JOBS"
log "  Rsync options: $RSYNC_OPTS"

# Build exclude options
EXCLUDE_OPTS=""
if [ -n "$SYNC_EXCLUDE" ]; then
    IFS=',' read -ra EXCLUDES <<< "$SYNC_EXCLUDE"
    for pattern in "${EXCLUDES[@]}"; do
        EXCLUDE_OPTS="$EXCLUDE_OPTS --exclude='$pattern'"
    done
    log "  Excludes: $SYNC_EXCLUDE"
fi

# Ensure source and destination exist
if [ ! -d "$SOURCE" ]; then
    log "ERROR: Source directory does not exist: $SOURCE"
    exit 1
fi

mkdir -p "$DEST"

# Method 1: Parallel rsync by top-level directories
# This distributes work across multiple rsync processes
parallel_by_dirs() {
    log "Using parallel-by-directories method"

    # Find top-level directories and files
    cd "$SOURCE"

    # Get list of items to sync
    ITEMS=$(find . -maxdepth 1 -mindepth 1 2>/dev/null | sed 's|^\./||')

    if [ -z "$ITEMS" ]; then
        log "No items to sync in $SOURCE"
        return 0
    fi

    ITEM_COUNT=$(echo "$ITEMS" | wc -l)
    log "Found $ITEM_COUNT items to sync"

    # Create a temporary file with the list
    ITEM_LIST=$(mktemp)
    echo "$ITEMS" > "$ITEM_LIST"

    # Use GNU parallel to run rsync jobs
    # Each job handles one top-level item (file or directory)
    cat "$ITEM_LIST" | parallel -j "$JOBS" --bar \
        "rsync $RSYNC_OPTS $EXCLUDE_OPTS '${SOURCE}{}' '${DEST}' 2>&1 | tee -a $LOG_FILE"

    RESULT=$?
    rm -f "$ITEM_LIST"

    return $RESULT
}

# Method 2: Single rsync with internal parallelism (simpler, for smaller datasets)
single_rsync() {
    log "Using single-rsync method"

    eval rsync $RSYNC_OPTS $EXCLUDE_OPTS "$SOURCE" "$DEST" 2>&1 | tee -a "$LOG_FILE"

    return $?
}

# Method 3: Parallel rsync by file chunks (for large flat directories)
parallel_by_files() {
    log "Using parallel-by-files method"

    # Create file list
    FILE_LIST=$(mktemp)
    find "$SOURCE" -type f > "$FILE_LIST"

    TOTAL_FILES=$(wc -l < "$FILE_LIST")
    log "Found $TOTAL_FILES files to sync"

    if [ "$TOTAL_FILES" -eq 0 ]; then
        log "No files to sync"
        rm -f "$FILE_LIST"
        return 0
    fi

    # Use parallel with rsync for each file, preserving relative paths
    cat "$FILE_LIST" | parallel -j "$JOBS" --bar \
        "rsync $RSYNC_OPTS --relative '{}' '${DEST}' 2>&1"

    RESULT=$?
    rm -f "$FILE_LIST"

    return $RESULT
}

# Choose method based on directory structure
# Count top-level items
TOP_LEVEL_COUNT=$(find "$SOURCE" -maxdepth 1 -mindepth 1 2>/dev/null | wc -l)

START_TIME=$(date +%s)

if [ "$TOP_LEVEL_COUNT" -eq 0 ]; then
    log "Source directory is empty, nothing to sync"
elif [ "$TOP_LEVEL_COUNT" -lt 3 ]; then
    # Few top-level items - use single rsync
    single_rsync
elif [ "$TOP_LEVEL_COUNT" -ge 3 ]; then
    # Multiple top-level items - parallel by directories
    parallel_by_dirs
fi

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

log "Sync completed in ${DURATION} seconds"

# Show sync statistics
log "Sync statistics:"
if command -v du &> /dev/null; then
    SOURCE_SIZE=$(du -sh "$SOURCE" 2>/dev/null | cut -f1)
    DEST_SIZE=$(du -sh "$DEST" 2>/dev/null | cut -f1)
    log "  Source size: $SOURCE_SIZE"
    log "  Destination size: $DEST_SIZE"
fi
