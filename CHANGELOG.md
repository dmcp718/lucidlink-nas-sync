# Changelog

All notable changes to LucidLink NAS Sync will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-01-19

### Added
- Web UI for managing sync jobs
- Parallel rsync workers for faster syncing
- Real-time progress tracking with `--info=progress2`
- Dry run preview before syncing
- Filename issues detection (problematic characters)
- Graceful job shutdown
- LucidLink filespace mounting
- Job persistence across container restarts

### Changed
- Removed automatic sync on startup - all syncing is now user-initiated via Web UI
- Fixed table column widths to prevent UI jitter

### Security
- Removed SYNC_INTERVAL and related environment variables that could sync entire volumes
