# MXCP Audit Cleanup with systemd

This directory contains example systemd service and timer files for scheduling automatic audit log cleanup.

## Installation

1. Copy the service and timer files to the systemd directory:
   ```bash
   sudo cp mxcp-audit-cleanup.service /etc/systemd/system/
   sudo cp mxcp-audit-cleanup.timer /etc/systemd/system/
   ```

2. Edit the service file to match your environment:
   ```bash
   sudo nano /etc/systemd/system/mxcp-audit-cleanup.service
   ```
   
   Update these values:
   - `User=` and `Group=` - Set to your MXCP user
   - `WorkingDirectory=` - Path to your MXCP project
   - `ReadWritePaths=` - Path to your audit directory
   - `ExecStart=` - Full path to mxcp command if not in PATH

3. Reload systemd and enable the timer:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable mxcp-audit-cleanup.timer
   sudo systemctl start mxcp-audit-cleanup.timer
   ```

## Usage

Check timer status:
```bash
systemctl status mxcp-audit-cleanup.timer
systemctl list-timers mxcp-audit-cleanup.timer
```

Run cleanup manually:
```bash
sudo systemctl start mxcp-audit-cleanup.service
```

View logs:
```bash
journalctl -u mxcp-audit-cleanup.service
```

## Cron Alternative

If you prefer cron over systemd, add this to your crontab:
```bash
# Run audit cleanup daily at 2 AM
0 2 * * * cd /path/to/your/mxcp/project && /usr/bin/mxcp audit cleanup
```

## Multiple Profiles

To run cleanup for multiple profiles, create separate service files:
```bash
# mxcp-audit-cleanup-prod.service
ExecStart=/usr/bin/mxcp audit cleanup --profile prod

# mxcp-audit-cleanup-dev.service  
ExecStart=/usr/bin/mxcp audit cleanup --profile dev
```
