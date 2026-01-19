# LucidLink Sync Container for TrueNAS SCALE

A Docker container for synchronizing files between TrueNAS SCALE storage and a LucidLink filespace using parallel rsync jobs.

## Features

- Parallel rsync synchronization for improved performance
- Configurable sync direction (push, pull, or bidirectional)
- Automatic sync at configurable intervals
- Designed for TrueNAS SCALE deployment
- FUSE support for LucidLink client

## Requirements

- TrueNAS SCALE 22.02+ (or any Docker host with FUSE support)
- LucidLink filespace credentials
- Container must run with:
  - `--privileged` OR `--cap-add SYS_ADMIN`
  - `--device /dev/fuse`

## Quick Start (Docker)

### 1. Build the Image

```bash
docker build -t lucidlink-sync:latest .
```

### 2. Create Environment File

```bash
cp .env.example .env
# Edit .env with your LucidLink credentials
```

### 3. Run with Docker Compose

```bash
docker compose up -d
```

### Or Run Directly

```bash
docker run -d \
  --name lucidlink-sync \
  --privileged \
  --cap-add SYS_ADMIN \
  --device /dev/fuse \
  -e LUCIDLINK_FILESPACE="your-filespace.domain" \
  -e LUCIDLINK_USER="your-username" \
  -e LUCIDLINK_PASSWORD="your-password" \
  -e SYNC_DIRECTION="local-to-filespace" \
  -e SYNC_INTERVAL="300" \
  -e PARALLEL_JOBS="4" \
  -v /path/to/local/data:/data/local \
  lucidlink-sync:latest
```

## TrueNAS SCALE Deployment

See [truenas-scale/TRUENAS_DEPLOYMENT.md](truenas-scale/TRUENAS_DEPLOYMENT.md) for detailed instructions.

**Key Configuration for TrueNAS SCALE:**

1. Enable **Privileged Mode**
2. Add capabilities: `SYS_ADMIN`, `MKNOD`
3. Mount `/dev/fuse` as host path
4. Mount your data directory to `/data/local`

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `LUCIDLINK_FILESPACE` | Yes | - | Filespace name (e.g., `myspace.domain`) |
| `LUCIDLINK_USER` | Yes | - | LucidLink username |
| `LUCIDLINK_PASSWORD` | Yes | - | LucidLink password |
| `LUCIDLINK_MOUNT_POINT` | No | `/data/filespace` | Container mount point for filespace |
| `LOCAL_DATA_PATH` | No | `/data/local` | Container path for local data |
| `SYNC_DIRECTION` | No | `local-to-filespace` | Sync direction (see below) |
| `SYNC_INTERVAL` | No | `300` | Seconds between syncs (0 or "once" for single run) |
| `PARALLEL_JOBS` | No | `4` | Number of parallel rsync processes |
| `RSYNC_OPTIONS` | No | `-avz --progress` | rsync command options |
| `SYNC_EXCLUDE` | No | - | Comma-separated exclude patterns |

### Sync Directions

| Value | Description |
|-------|-------------|
| `local-to-filespace` | Copy from local storage to LucidLink |
| `filespace-to-local` | Copy from LucidLink to local storage |
| `bidirectional` | Sync both directions (local first) |

Aliases: `push` = `local-to-filespace`, `pull` = `filespace-to-local`, `both` = `bidirectional`

## Volume Mounts

| Container Path | Purpose |
|---------------|---------|
| `/data/local` | Your local data directory |
| `/data/filespace` | LucidLink mount (internal) |
| `/dev/fuse` | FUSE device (required) |
| `/var/log/sync` | Sync logs (optional) |

## Logs

Logs are written to `/var/log/sync/`:

- `container.log` - Main container/daemon logs
- `sync.log` - Sync operation logs
- `parallel-rsync.log` - Detailed rsync logs

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    TrueNAS SCALE                            │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              lucidlink-sync container                 │  │
│  │  ┌─────────────┐    ┌─────────────┐                  │  │
│  │  │  LucidLink  │    │  Parallel   │                  │  │
│  │  │   Daemon    │◄──►│   Rsync     │                  │  │
│  │  └──────┬──────┘    └──────┬──────┘                  │  │
│  │         │                  │                          │  │
│  │         ▼                  ▼                          │  │
│  │  /data/filespace    /data/local                       │  │
│  │      (FUSE)          (bind mount)                     │  │
│  └───────────────────────────────────────────────────────┘  │
│                              │                              │
│                              ▼                              │
│              /mnt/pool-z/data1/backup_misc                  │
│                     (TrueNAS dataset)                       │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ Internet
                              ▼
                    ┌─────────────────┐
                    │    LucidLink    │
                    │     Cloud       │
                    └─────────────────┘
```

## Parallel Sync Algorithm

The sync process uses parallel workers to maximize throughput. Here's how batches are created and distributed:

### 1. Pre-scan Phase

Before syncing, the system scans the source directory:
- Counts total files and calculates total size
- Identifies all top-level items (files and directories)
- Calculates file count and byte size for each item

### 2. Batch Distribution

Items are distributed across workers using **greedy load balancing by size**:

```
Algorithm:
1. Sort all top-level items by size (largest first)
2. For each item:
   - Find the worker with the smallest current load (total bytes)
   - Assign the item to that worker
3. Continue until all items are assigned
```

**Example:** 4 workers, 6 items with sizes [500MB, 300MB, 200MB, 150MB, 100MB, 50MB]

```
Step 1: Assign 500MB → Worker 0 (loads: [500, 0, 0, 0])
Step 2: Assign 300MB → Worker 1 (loads: [500, 300, 0, 0])
Step 3: Assign 200MB → Worker 2 (loads: [500, 300, 200, 0])
Step 4: Assign 150MB → Worker 3 (loads: [500, 300, 200, 150])
Step 5: Assign 100MB → Worker 3 (loads: [500, 300, 200, 250])
Step 6: Assign 50MB  → Worker 2 (loads: [500, 300, 250, 250])

Final distribution:
  Worker 0: 500MB (1 item)
  Worker 1: 300MB (1 item)
  Worker 2: 250MB (2 items)
  Worker 3: 250MB (2 items)
```

### 3. Worker Execution

Each worker:
- Receives its assigned items (directories or files)
- Runs independent rsync processes for each item
- Reports progress after completing each item
- Errors are collected and logged per-worker

### 4. Progress Tracking

The UI displays:
- **Total progress:** Files transferred / Total files
- **Total size:** Calculated before sync starts
- **Worker status:** Each worker shows its current item and progress
- **Active workers:** Count of workers still running

### Why Top-Level Distribution?

Distributing at the top-level (rather than individual files) provides:
- **Better rsync efficiency:** Each worker can use rsync's delta transfer within its items
- **Reduced overhead:** Fewer rsync process startups
- **Natural batching:** Directories are kept together, preserving locality
- **Simpler progress tracking:** Progress updates per-item completion

**Note:** If you have a single large directory with many files, consider organizing into subdirectories for better parallelization.

## TrueNAS SCALE Compatibility

**Will LucidLink work in TrueNAS SCALE containers?**

Yes, with proper configuration:

| Requirement | TrueNAS SCALE Support |
|-------------|----------------------|
| Privileged mode | Supported via Custom App |
| SYS_ADMIN capability | Supported |
| /dev/fuse device | Can be mounted as host path |
| Network access | Supported |

TrueNAS SCALE uses Kubernetes (k3s) under the hood. The Custom App feature allows deploying containers with the necessary privileged security context.

## Building for Different Architectures

```bash
# Build for AMD64 (default)
docker build -t lucidlink-sync:latest .

# Build for ARM64 (if LucidLink supports it)
docker build --platform linux/arm64 -t lucidlink-sync:arm64 .
```

## Troubleshooting

### Container won't start - FUSE error

```
ERROR: /dev/fuse not available
```

Ensure the container has:
- Privileged mode enabled, OR
- `SYS_ADMIN` capability AND `/dev/fuse` device mounted

### LucidLink connection fails

1. Verify credentials are correct
2. Check filespace name is fully qualified (includes domain)
3. Ensure outbound internet connectivity

### Sync not running

Check logs:
```bash
docker logs lucidlink-sync
```

Common issues:
- Source directory empty
- Invalid sync direction
- rsync errors (check `/var/log/sync/parallel-rsync.log`)

## License

MIT
