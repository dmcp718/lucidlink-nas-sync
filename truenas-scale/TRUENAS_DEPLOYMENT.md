# TrueNAS SCALE Deployment Guide

This guide covers deploying the LucidLink Sync container on TrueNAS SCALE using the Custom App feature.

> **Reference**: [TrueNAS Custom App Documentation](https://apps.truenas.com/managing-apps/installing-custom-apps/)

## Prerequisites

1. **TrueNAS SCALE** 24.04 "Dragonfish" or later
2. **LucidLink filespace** with valid credentials
3. **Dataset** for local data storage (e.g., `/mnt/pool/data/backup`)
4. **Dataset** for app config persistence (e.g., `/mnt/pool/apps/lucidlink-sync`)

## Quick Overview

| Component | Details |
|-----------|---------|
| Container Image | `lucidlink-sync:latest` |
| Web UI Port | `8080` |
| Required Security | Privileged Mode + `SYS_ADMIN` + `MKNOD` |
| Required Device | `/dev/fuse` |
| Data Mount | Your data directory → `/data/local` |
| Config Mount | Persistent storage → `/config` |

---

## Step 1: Build the Docker Image

SSH into your TrueNAS server and build the image locally:

```bash
# SSH to TrueNAS
ssh admin@YOUR_TRUENAS_IP

# Create a temporary build directory
mkdir -p /tmp/lucidlink-build
cd /tmp/lucidlink-build

# Option A: Clone from git
git clone https://github.com/dmcp718/lucidlink-nas-sync.git .

# Option B: Copy files via SCP from your workstation
# scp -r /path/to/lucidlink-sync/* admin@YOUR_TRUENAS_IP:/tmp/lucidlink-build/

# Build the Docker image
docker build -t lucidlink-sync:latest .

# Verify the image exists
docker images | grep lucidlink-sync
```

---

## Step 2: Create Datasets for Persistent Storage

In TrueNAS Web UI:

1. Go to **Datasets**
2. Create a dataset for app data: `pool/apps/lucidlink-sync`
3. Create subdirectories via SSH:
   ```bash
   mkdir -p /mnt/pool/apps/lucidlink-sync/{config,logs,cache}
   ```

---

## Step 3: Deploy via Custom App

1. Navigate to **Apps** in TrueNAS Web UI
2. Click **Discover Apps** → **Custom App**

---

### Application Name

| Field | Value |
|-------|-------|
| **Application Name** | `lucidlink-sync` |
| **Version** | `1.0.0` (or leave default) |

---

### Image Configuration

| Field | Value |
|-------|-------|
| **Image Repository** | `lucidlink-sync` |
| **Tag** | `latest` |
| **Pull Policy** | `Never` (local image) |

> **Note**: Use `Never` since we built the image locally. Use `Always` or `IfNotPresent` if pulling from a registry.

---

### Container Configuration

#### Hostname
Leave empty (optional)

#### Entrypoint
Leave empty (uses container default: `/scripts/entrypoint.sh`)

#### Command
Leave empty (uses container default)

#### Timezone
Select your timezone (e.g., `America/Chicago`)

#### Environment Variables

Click **Add** for each variable:

| Name | Value |
|------|-------|
| `LUCIDLINK_FILESPACE` | `your-filespace.domain` |
| `LUCIDLINK_USER` | `your-username` |
| `LUCIDLINK_PASSWORD` | `your-password` |
| `LUCIDLINK_MOUNT_POINT` | `/data/filespace` |
| `LOCAL_DATA_PATH` | `/data/local` |
| `SYNC_INTERVAL` | `0` |
| `PARALLEL_JOBS` | `4` |
| `WEBUI_ENABLED` | `true` |
| `WEBUI_PORT` | `8080` |

> **Tip**: Set `SYNC_INTERVAL=0` to disable automatic sync. Use the Web UI to create and manage sync jobs instead.

#### Restart Policy
Select: `Unless Stopped`

#### Other Options
| Option | Value |
|--------|-------|
| **Disable Builtin Healthcheck** | Leave unchecked |
| **TTY** | Leave unchecked |
| **Stdin** | Leave unchecked |

#### Devices

Click **Add** to add the FUSE device:

| Field | Value |
|-------|-------|
| **Host Device** | `/dev/fuse` |
| **Container Device** | `/dev/fuse` |

---

### Security Context Configuration

This section is **CRITICAL** for LucidLink/FUSE to work.

#### Privileged
| Field | Value |
|-------|-------|
| **Privileged** | ✓ **Enabled** |

> **Warning**: Privileged mode grants full host device access. Required for FUSE filesystem.

#### Capabilities

Click **Add** for each capability:

| Capability |
|------------|
| `SYS_ADMIN` |
| `MKNOD` |

#### Custom User
Leave unchecked (use container defaults)

---

### Network Configuration

#### Host Network
Leave unchecked (we'll use port mapping)

#### Ports

Click **Add** under Ports:

| Field | Value |
|-------|-------|
| **Container Port** | `8080` |
| **Host Port** | `8080` |
| **Protocol** | `TCP` |

#### Custom DNS Setup
Leave all empty (use system defaults):
- **Nameservers**: (none)
- **Search Domains**: (none)
- **DNS Options**: (none)

---

### Portal Configuration

Click **Add** to create a Web UI portal link:

| Field | Value |
|-------|-------|
| **Name** | `Web UI` |
| **Protocol** | `HTTP` |
| **Host** | `$node_ip` (or leave default) |
| **Port** | `8080` |
| **Path** | `/` |

This adds a clickable "Web UI" button in the Apps list.

---

### Storage Configuration

Click **Add** under Storage for each mount:

#### 1. Local Data Directory

| Field | Value |
|-------|-------|
| **Type** | `Host Path` |
| **Host Path** | `/mnt/pool/data/backup` (your data location) |
| **Mount Path** | `/data/local` |
| **Read Only** | Unchecked |

#### 2. Config Persistence

| Field | Value |
|-------|-------|
| **Type** | `Host Path` |
| **Host Path** | `/mnt/pool/apps/lucidlink-sync/config` |
| **Mount Path** | `/config` |
| **Read Only** | Unchecked |

#### 3. Log Persistence (Optional)

| Field | Value |
|-------|-------|
| **Type** | `Host Path` |
| **Host Path** | `/mnt/pool/apps/lucidlink-sync/logs` |
| **Mount Path** | `/var/log/sync` |
| **Read Only** | Unchecked |

#### 4. LucidLink Cache (Optional but Recommended)

| Field | Value |
|-------|-------|
| **Type** | `Host Path` |
| **Host Path** | `/mnt/pool/apps/lucidlink-sync/cache` |
| **Mount Path** | `/cache` |
| **Read Only** | Unchecked |

---

### Labels Configuration

Leave empty (optional, for container labeling)

---

### Resources Configuration

#### Enable Resource Limits
Optionally enable and configure:

| Field | Value |
|-------|-------|
| **CPU** | `4` (4 cores) |
| **Memory** | `4096` (MB) |

#### GPU Configuration
Leave unchecked (not required)

---

## Step 4: Install

Click **Install** to deploy the application.

Monitor the deployment in the Apps list. The container should start within 30-60 seconds.

---

## Step 5: Access the Web UI

Once deployed, access the Web UI:

**Option A**: Click the **Web UI** portal button in the Apps list

**Option B**: Navigate directly to:
```
http://YOUR_TRUENAS_IP:8080
```

---

## Web UI Features

| Feature | Description |
|---------|-------------|
| **Sync Jobs** | Create, edit, start, stop sync jobs |
| **File Browser** | Browse local and LucidLink filespace |
| **Path Picker** | Select source/destination paths with Browse button |
| **Progress Tracking** | Real-time sync progress with parallel worker status |
| **Filename Issues** | Detect and fix problematic filenames |
| **Logs** | View container, sync, and error logs |

### Creating a Sync Job

1. Open Web UI at `http://YOUR_TRUENAS_IP:8080`
2. Click **New Job**
3. Configure:
   - **Name**: Descriptive name (e.g., "Backup to Cloud")
   - **Source Path**: Click **Browse** to select
   - **Destination Path**: Click **Browse** to select
   - **Direction**: `local-to-filespace`, `filespace-to-local`, or `bidirectional`
   - **Parallel Jobs**: Number of workers (default: 4)
4. Click **Create Job**
5. Click **Start** to run the sync

---

## Alternative: Docker CLI Deployment

For direct Docker deployment via SSH:

```bash
# SSH to TrueNAS
ssh admin@YOUR_TRUENAS_IP

# Create directories
mkdir -p /mnt/pool/apps/lucidlink-sync/{config,logs,cache}

# Run the container
docker run -d \
  --name lucidlink-sync \
  --privileged \
  --cap-add SYS_ADMIN \
  --cap-add MKNOD \
  --device /dev/fuse:/dev/fuse \
  --restart unless-stopped \
  -p 8080:8080 \
  -e TZ="America/Chicago" \
  -e LUCIDLINK_FILESPACE="your-filespace.domain" \
  -e LUCIDLINK_USER="your-username" \
  -e LUCIDLINK_PASSWORD="your-password" \
  -e SYNC_INTERVAL="0" \
  -e WEBUI_ENABLED="true" \
  -v /mnt/pool/data/backup:/data/local \
  -v /mnt/pool/apps/lucidlink-sync/config:/config \
  -v /mnt/pool/apps/lucidlink-sync/logs:/var/log/sync \
  -v /mnt/pool/apps/lucidlink-sync/cache:/cache \
  lucidlink-sync:latest
```

---

## Verification

### Check Container Status

```bash
# View running containers
docker ps | grep lucidlink-sync

# View logs
docker logs -f lucidlink-sync

# Check LucidLink connection
docker exec -it lucidlink-sync lucid status

# Verify filespace mount
docker exec -it lucidlink-sync ls -la /data/filespace/
```

### Health Check

```bash
curl http://YOUR_TRUENAS_IP:8080/health
```

Expected response:
```json
{"status":"healthy","webui_enabled":true,"lucidlink_mount":"/data/filespace","local_path":"/data/local"}
```

---

## Troubleshooting

### FUSE Device Not Available

**Error**: `/dev/fuse not available`

**Solution**:
1. Add `/dev/fuse` under **Devices** in Container Configuration
2. Ensure **Privileged** mode is enabled in Security Context
3. Add `SYS_ADMIN` and `MKNOD` capabilities

### Permission Denied on /dev/fuse

**Error**: `fuse: failed to open /dev/fuse: Permission denied`

**Solution**:
1. Enable **Privileged** mode (required for FUSE)
2. Redeploy the app after changing security settings

### LucidLink Connection Fails

**Error**: `Failed to connect to filespace`

**Solution**:
1. Verify credentials are correct
2. Check filespace name is fully qualified (e.g., `myspace.lucid.link`)
3. Test network: `docker exec lucidlink-sync ping -c 3 google.com`

### Web UI Not Accessible

**Symptoms**: Cannot reach `http://IP:8080`

**Solution**:
1. Verify port 8080 is mapped in Network Configuration → Ports
2. Check container is running: `docker ps | grep lucidlink`
3. Check logs: `docker logs lucidlink-sync`
4. Verify firewall allows port 8080

### Sync Jobs Disappear After Restart

**Solution**: Ensure `/config` is mounted to a Host Path (not Tmpfs or ixVolume).

### Container Keeps Restarting

Check logs for specific errors:
```bash
docker logs lucidlink-sync
```

Common causes:
- Invalid LucidLink credentials
- FUSE not available (check Devices and Privileged mode)
- Missing required environment variables

---

## Security Considerations

1. **Privileged Mode**: Required for FUSE. Only deploy containers you trust.

2. **Credentials**: Stored as environment variables. For production:
   - Restrict TrueNAS admin access
   - Consider using a dedicated LucidLink service account
   - Rotate credentials periodically

3. **Network**:
   - Outbound: Container needs internet access for LucidLink cloud
   - Inbound: Port 8080 for Web UI (restrict to trusted networks)

4. **Data Access**: Mount only the directories the container needs.

---

## Updating the Container

```bash
# SSH to TrueNAS
ssh admin@YOUR_TRUENAS_IP

# Rebuild the image
cd /tmp/lucidlink-build
git pull
docker build -t lucidlink-sync:latest .

# Restart via TrueNAS Apps UI:
# 1. Stop the app
# 2. Start the app (it will use the new image)
```

---

## Environment Variable Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `LUCIDLINK_FILESPACE` | Yes | - | Filespace name (e.g., `myspace.lucid.link`) |
| `LUCIDLINK_USER` | Yes | - | LucidLink username |
| `LUCIDLINK_PASSWORD` | Yes | - | LucidLink password |
| `LUCIDLINK_MOUNT_POINT` | No | `/data/filespace` | Container mount for filespace |
| `LOCAL_DATA_PATH` | No | `/data/local` | Container path for local data |
| `SYNC_DIRECTION` | No | `local-to-filespace` | Default sync direction |
| `SYNC_INTERVAL` | No | `300` | Seconds between auto-syncs (0=disabled) |
| `PARALLEL_JOBS` | No | `4` | Number of parallel rsync workers |
| `RSYNC_OPTIONS` | No | `-avz --progress` | rsync command options |
| `SYNC_EXCLUDE` | No | - | Comma-separated exclude patterns |
| `WEBUI_ENABLED` | No | `true` | Enable/disable Web UI |
| `WEBUI_PORT` | No | `8080` | Web UI port |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      TrueNAS SCALE                               │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                lucidlink-sync container                      ││
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       ││
│  │  │   Web UI     │  │  LucidLink   │  │   Parallel   │       ││
│  │  │   :8080      │  │   Daemon     │  │    Rsync     │       ││
│  │  └──────────────┘  └──────┬───────┘  └──────┬───────┘       ││
│  │                           │                  │               ││
│  │         /data/filespace ◄─┘                  └─► /data/local ││
│  │            (FUSE)                              (bind mount)  ││
│  └─────────────────────────────────────────────────────────────┘│
│                  │                                    │          │
│                  │                                    ▼          │
│                  │              /mnt/pool/data/backup            │
│                  │                 (TrueNAS dataset)             │
└──────────────────┼──────────────────────────────────────────────┘
                   │
                   │ Internet (HTTPS)
                   ▼
          ┌─────────────────┐
          │    LucidLink    │
          │     Cloud       │
          └─────────────────┘
```
