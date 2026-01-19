# TrueNAS SCALE Deployment Guide

This guide covers deploying the LucidLink Sync container on TrueNAS SCALE.

## Prerequisites

1. TrueNAS SCALE 22.02 or later
2. A LucidLink filespace with valid credentials
3. A dataset for local data storage (e.g., `/mnt/pool-z/data1/backup_misc`)

## Option 1: Custom App via TrueNAS Web UI (Recommended)

### Step 1: Build and Push the Image

First, build the Docker image and push it to a registry accessible by your TrueNAS server:

```bash
# Build the image
docker build -t lucidlink-sync:latest .

# Tag for your registry (example using Docker Hub)
docker tag lucidlink-sync:latest yourusername/lucidlink-sync:latest

# Push to registry
docker push yourusername/lucidlink-sync:latest
```

Alternatively, build directly on TrueNAS if you have SSH access:

```bash
# SSH to TrueNAS
ssh root@192.168.8.160

# Clone or copy the project
cd /tmp
# ... copy files ...

# Build using Docker (TrueNAS SCALE includes Docker)
docker build -t lucidlink-sync:latest .
```

### Step 2: Deploy via TrueNAS Web UI

1. Navigate to **Apps** in the TrueNAS SCALE web interface
2. Click **Discover Apps** → **Custom App**
3. Configure the following settings:

#### Application Name
- Name: `lucidlink-sync`

#### Container Images
- Image repository: `lucidlink-sync` (or your registry path)
- Image tag: `latest`
- Image Pull Policy: `IfNotPresent`

#### Container Entrypoint
- Leave default (uses `/scripts/entrypoint.sh`)

#### Container Environment Variables

Add the following environment variables:

| Name | Value |
|------|-------|
| LUCIDLINK_FILESPACE | `your-filespace.domain` |
| LUCIDLINK_USER | `your-username` |
| LUCIDLINK_PASSWORD | `your-password` |
| LUCIDLINK_MOUNT_POINT | `/data/filespace` |
| LOCAL_DATA_PATH | `/data/local` |
| SYNC_DIRECTION | `local-to-filespace` |
| SYNC_INTERVAL | `300` |
| PARALLEL_JOBS | `4` |
| RSYNC_OPTIONS | `-avz --progress` |
| SYNC_EXCLUDE | `.DS_Store,Thumbs.db,*.tmp` |

#### Security Context (CRITICAL)

This section is essential for FUSE support:

1. Check **Privileged Mode** ✓
2. Under **Capabilities**, add:
   - `SYS_ADMIN`
   - `MKNOD`

#### Storage

Add the following host path volumes:

| Host Path | Mount Path | Description |
|-----------|------------|-------------|
| `/dev/fuse` | `/dev/fuse` | FUSE device (required) |
| `/mnt/pool-z/data1/backup_misc` | `/data/local` | Your data directory |

For the `/dev/fuse` mount:
- Type: **Host Path**
- Host Path: `/dev/fuse`
- Mount Path: `/dev/fuse`

For the data mount:
- Type: **Host Path**
- Host Path: `/mnt/pool-z/data1/backup_misc`
- Mount Path: `/data/local`
- Read Only: No

#### Resource Limits (Optional)

- CPU: 2000m (2 cores)
- Memory: 2Gi

### Step 3: Deploy

Click **Install** to deploy the application.

## Option 2: Deploy via CLI (kubectl)

If you have kubectl access to the TrueNAS SCALE Kubernetes cluster:

```bash
# Apply the deployment manifest
kubectl apply -f truenas-scale/deployment.yaml

# Check deployment status
kubectl -n lucidlink-sync get pods

# View logs
kubectl -n lucidlink-sync logs -f deployment/lucidlink-sync
```

## Verifying the Deployment

### Check Container Logs

Via TrueNAS UI:
1. Go to **Apps** → **lucidlink-sync**
2. Click **View Logs**

Via CLI:
```bash
# SSH to TrueNAS
ssh root@192.168.8.160

# Find the container
docker ps | grep lucidlink

# View logs
docker logs -f <container_id>
```

### Verify LucidLink Connection

```bash
# Exec into container
docker exec -it <container_id> bash

# Check LucidLink status
lucid status

# Verify mount
ls -la /data/filespace/
```

## Troubleshooting

### FUSE Device Not Available

**Error**: `/dev/fuse not available`

**Solution**: Ensure privileged mode is enabled and `/dev/fuse` is mounted as a host path.

### Permission Denied

**Error**: `fuse: failed to open /dev/fuse: Permission denied`

**Solution**:
1. Enable **Privileged Mode**
2. Add `SYS_ADMIN` capability
3. Verify `/dev/fuse` host path mount

### LucidLink Daemon Won't Start

**Error**: `Failed to connect to filespace`

**Solution**:
1. Verify credentials are correct
2. Check network connectivity from container
3. Ensure filespace name is fully qualified (includes domain)

### Container Keeps Restarting

Check logs for specific errors:
```bash
docker logs <container_id>
```

Common causes:
- Invalid credentials
- Missing environment variables
- FUSE not available

## Security Considerations

1. **Credentials**: Store LucidLink credentials securely. Consider using TrueNAS's secret management.

2. **Privileged Mode**: This container runs in privileged mode. Only deploy if you trust the container contents.

3. **Network**: The container needs outbound internet access to connect to LucidLink cloud services.

## Sync Behavior

| Direction | Behavior |
|-----------|----------|
| `local-to-filespace` | Copies from TrueNAS storage to LucidLink |
| `filespace-to-local` | Copies from LucidLink to TrueNAS storage |
| `bidirectional` | Syncs both directions (local first, then filespace) |

The sync runs every `SYNC_INTERVAL` seconds (default: 300 = 5 minutes).
