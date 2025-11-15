# Reolink AIO Examples

This directory contains example scripts demonstrating how to use the `reolink_aio` library.

## Setup

### Option 1: Docker (Recommended)

1. **Copy the example configuration:**
   ```bash
   cp .env.example .env
   ```

2. **Edit `.env` with your camera details:**
   ```bash
   # Required settings
   CAMERA_HOST=192.168.1.10       # Your camera IP address
   CAMERA_USERNAME=admin           # Camera username
   CAMERA_PASSWORD=yourpassword    # Camera password

   # Optional settings (defaults shown)
   CAMERA_PORT=80                  # HTTP port
   CAMERA_CHANNEL=0                # Channel number (0 for standalone camera)
   MONITOR_DURATION=0              # Seconds to monitor (0 = infinite)
   HISTORY_HOURS=24                # Hours of historical recordings to search
   DOWNLOAD_RECORDINGS=false       # Whether to download recordings
   DOWNLOAD_PATH=./recordings      # Where to save downloaded files
   ```

3. **Run with Docker Compose:**
   ```bash
   docker-compose up -d
   ```

4. **View logs:**
   ```bash
   docker-compose logs -f
   ```

5. **Stop the container:**
   ```bash
   docker-compose down
   ```

### Option 2: Local Python Installation

1. **Copy the example configuration:**
   ```bash
   cp .env.example .env
   ```

2. **Edit `.env` with your camera details** (see above)

3. **Install dependencies:**
   ```bash
   pip install -r ../requirements.txt
   pip install twilio  # Optional, for SMS notifications
   ```

4. **Run the script:**
   ```bash
   python retrieve_motion_events.py
   ```

## Examples

### retrieve_motion_events.py

Comprehensive example demonstrating how to retrieve motion events from a Reolink camera.

**Features:**
- Connects to camera and displays device info
- Checks if motion detection and recording are enabled
- Shows recording calendar (which days have recordings)
- Searches for historical motion recordings
- Optionally downloads recordings
- Monitors real-time motion events via Baichuan TCP
- Provides detailed logging of all events

**Usage:**
```bash
python retrieve_motion_events.py
```

**Example Output:**
```
2024-01-15 10:30:00 - INFO - Connecting to camera...
2024-01-15 10:30:01 - INFO - Connected to: Reolink RLC-810A
2024-01-15 10:30:01 - INFO - Model: RLC-810A
2024-01-15 10:30:01 - INFO - Firmware: v3.1.0.956_23012701
2024-01-15 10:30:01 - INFO - Channels: [0]
2024-01-15 10:30:01 - INFO - Motion detection is enabled on channel 0
2024-01-15 10:30:01 - INFO - Sensitivity level: 50

Recording Calendar:
2024-01: 15 days with recordings
  Days: 1, 2, 3, 5, 8, 10, 12, 13, 14, 15, 16, 18, 20, 22, 25

Searching for recordings from 2024-01-14 10:30:00 to 2024-01-15 10:30:00

Recording #1:
  Start: 2024-01-15 08:15:23
  End: 2024-01-15 08:18:45
  Duration: 0:03:22
  Size: 15,234,567 bytes (14.53 MB)
  Stream: main
  Triggers: Motion, Person

Starting real-time event monitoring for 300 seconds...
2024-01-15 10:35:12 - INFO - ⚡ MOTION STARTED on channel 0
2024-01-15 10:35:45 - INFO - ✓ MOTION ENDED on channel 0

Summary:
Historical recordings found: 12
Real-time events detected: 2
  Motion events: 1
```

**What it does:**

1. **Camera Info** - Displays camera model, firmware, channels
2. **Settings Check** - Verifies motion detection and recording are enabled
3. **Calendar View** - Shows which days have recordings (fast status check)
4. **Historical Search** - Finds motion recordings from last N hours
   - Filters by trigger type (motion, person, vehicle, etc.)
   - Shows detailed info for each recording
5. **Download** (optional) - Downloads recordings to local disk
6. **Real-time Monitor** - Subscribes to live motion events for N seconds
   - Uses efficient Baichuan TCP protocol
   - Detects motion start/end events
   - Logs all events with timestamps

**Run Indefinitely:**

To monitor motion events continuously until you stop it, set in `.env`:
```bash
MONITOR_DURATION=0
```

The script will run forever, logging events as they occur. Press Ctrl+C to stop.

**Customization:**

Edit the script or `.env` to change behavior:

```python
# Change trigger filter to get only person detections
trigger_filter=VOD_trigger.PERSON

# Or combine multiple triggers
trigger_filter=VOD_trigger.MOTION | VOD_trigger.PERSON | VOD_trigger.VEHICLE

# Limit number of recordings to download
max_downloads = 10

# Change monitoring duration
monitor_duration = 600  # 10 minutes
```

## Configuration Reference

| Variable | Description | Default |
|----------|-------------|---------|
| `CAMERA_HOST` | IP address or hostname of camera | Required |
| `CAMERA_USERNAME` | Camera username | `admin` |
| `CAMERA_PASSWORD` | Camera password | Required |
| `CAMERA_PORT` | HTTP port | `80` |
| `CAMERA_CHANNEL` | Channel number (0 for standalone camera, 0-N for NVR) | `0` |
| `MONITOR_DURATION` | Seconds to monitor for real-time events (0 = infinite) | `300` (5 min) |
| `HISTORY_HOURS` | Hours of history to search | `24` |
| `DOWNLOAD_RECORDINGS` | Whether to download recordings (`true`/`false`) | `false` |
| `DOWNLOAD_PATH` | Directory for downloaded recordings | `./recordings` |
| `BAICHUAN_LOG_LEVEL` | Baichuan logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL | `CRITICAL` |
| `TWILIO_ACCOUNT_SID` | Twilio Account SID (optional, for SMS alerts) | - |
| `TWILIO_AUTH_TOKEN` | Twilio Auth Token (optional) | - |
| `TWILIO_FROM_NUMBER` | Twilio phone number to send from (e.g., +15551234567) | - |
| `TWILIO_TO_NUMBER` | Your phone number to receive alerts (e.g., +15559876543) | - |
| `SMS_ON_MOTION` | Send SMS when motion detected (`true`/`false`) | `false` |
| `SMS_COOLDOWN` | Minimum seconds between SMS messages (prevents spam) | `300` (5 min) |
| `TOUCHFILE_PATH` | Path to file that triggers manual SMS when created | - |
| `TOUCHFILE_CHECK_INTERVAL` | How often to check for touchfile in seconds | `5` |
| `DISK_MONITOR_ENABLED` | Enable disk space monitoring and alerts (`true`/`false`) | `false` |
| `DISK_MONITOR_PATH` | Path to monitor (e.g., `/` for root filesystem) | `/` |
| `DISK_MONITOR_THRESHOLD` | Alert when disk usage exceeds this percentage | `90` |
| `DISK_MONITOR_CHECK_INTERVAL` | How often to check disk space in seconds | `3600` (1 hour) |

## SMS Notifications with Twilio

### Setup

1. **Create a Twilio account** at https://www.twilio.com/
2. **Get a phone number** from Twilio console
3. **Find your credentials**:
   - Account SID: Found in Twilio Console dashboard
   - Auth Token: Found in Twilio Console dashboard
4. **Install Twilio library**:
   ```bash
   pip install twilio
   ```

### Configuration

Edit your `.env` file:

```bash
# Twilio SMS notifications
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token_here
TWILIO_FROM_NUMBER=+15551234567  # Your Twilio number
TWILIO_TO_NUMBER=+15559876543    # Your cell phone

# Enable SMS on motion detection
SMS_ON_MOTION=true

# Prevent SMS spam - wait 5 minutes between alerts
SMS_COOLDOWN=300
```

### Features

- **Automatic SMS alerts** when motion is detected
- **Cooldown protection** - Won't spam you with repeated messages
- **Camera name in message** - Know which camera detected motion
- **Timestamp** - See exactly when motion occurred
- **Graceful fallback** - Script works fine without Twilio configured

### Example SMS Message

```
🚨 Motion detected on Front Door Camera at 14:35:22
```

### Cost

Twilio charges per SMS (typically $0.0075/message in US). With the default 5-minute cooldown, maximum cost would be ~$2.16/day if motion is constantly detected.

### Manual SMS Trigger (Touchfile)

The touchfile feature allows you to manually trigger an SMS alert by creating a file. This is useful for:
- Testing SMS notifications
- Manual alerts from other scripts or automation
- Integration with home automation systems
- Remote notifications via file sharing/sync

**Setup:**

Add to your `.env` file:
```bash
TOUCHFILE_PATH=/app/examples/trigger_sms.txt
TOUCHFILE_CHECK_INTERVAL=5  # Check every 5 seconds
```

**Usage:**

To trigger an SMS alert, simply create the file:

```bash
# Send alert with default message
touch /app/examples/trigger_sms.txt

# Or write a custom message
echo "Security alert: Front door opened" > /app/examples/trigger_sms.txt
```

The script will:
1. Detect the file within 5 seconds (or your configured interval)
2. Read the message from the file (or use a default message if empty)
3. Send the SMS immediately (bypasses cooldown)
4. Delete the file automatically after sending

**Docker Example:**

From outside the container:
```bash
# Create touchfile in mounted directory
docker-compose exec reolink-motion-monitor touch /app/examples/trigger_sms.txt

# Or with custom message
docker-compose exec reolink-motion-monitor sh -c 'echo "Pool area motion detected" > /app/examples/trigger_sms.txt'
```

**Features:**
- **No cooldown** - Manual triggers bypass the SMS cooldown period
- **Custom messages** - Write any message to the file
- **Auto-cleanup** - File is deleted after processing
- **Safe** - Won't spam even if created repeatedly (cooldown still applies to subsequent motion events)

**Integration Example:**

Use with cron, home automation, or other scripts:
```bash
#!/bin/bash
# Script to send alert when disk space is low
if [ $(df -h /recordings | tail -1 | awk '{print $5}' | sed 's/%//') -gt 90 ]; then
    echo "⚠️ Recording disk 90% full" > /app/examples/trigger_sms.txt
fi
```

### Disk Space Monitoring

The script includes built-in disk space monitoring that automatically sends SMS alerts when disk usage exceeds a threshold.

**Setup:**

Add to your `.env` file:
```bash
DISK_MONITOR_ENABLED=true
DISK_MONITOR_PATH=/                  # Monitor root filesystem
DISK_MONITOR_THRESHOLD=90            # Alert at 90% usage
DISK_MONITOR_CHECK_INTERVAL=3600     # Check every hour
```

**Features:**
- **Automatic monitoring** - Checks disk space at regular intervals
- **Threshold alerts** - Only sends SMS when usage exceeds configured percentage
- **Cooldown protection** - Uses same cooldown as motion alerts to prevent spam
- **Detailed info** - SMS includes used/free space in GB and percentage
- **Works on Linux** - Monitors any mounted filesystem path

**Example SMS Message:**
```
⚠️ Disk space alert: /
90.5% used (181.0GB / 200.0GB)
19.0GB free remaining
```

**Docker Setup for Host Monitoring:**

To monitor the host's root filesystem (not just container), uncomment this line in [docker-compose.yml](docker-compose.yml):
```yaml
volumes:
  - ./recordings:/app/examples/recordings
  - .:/app/examples/host
  - /:/host:ro  # Uncomment this line
```

Then set in `.env`:
```bash
DISK_MONITOR_PATH=/host  # Monitor host root filesystem
```

**Use Cases:**
- Monitor recording storage to prevent running out of space
- Alert before disk fills up completely
- Track storage usage on NAS or dedicated recording drives
- Integration with automated cleanup scripts

## Docker Deployment

### Why Docker?

- **Isolated environment** - No conflicts with system Python or other packages
- **Easy deployment** - Single command to start monitoring
- **Automatic restart** - Container restarts if it crashes or system reboots
- **Consistent behavior** - Same environment across different systems
- **Resource management** - Control CPU/memory usage

### Docker Commands

```bash
# Build and start in background
docker-compose up -d

# View real-time logs
docker-compose logs -f

# Stop the container
docker-compose down

# Restart the container
docker-compose restart

# Rebuild after code changes
docker-compose up -d --build

# View container status
docker-compose ps

# Access container shell (for debugging)
docker-compose exec reolink-motion-monitor bash
```

### Persistent Storage

The `recordings` directory is mounted as a volume, so downloaded recordings persist even if the container is removed:

```yaml
volumes:
  - ./recordings:/app/examples/recordings
```

### Network Configuration

By default, the container uses `network_mode: host` to access cameras on your local network. This is the simplest setup for home networks.

**Alternative: Bridge mode** (if you need network isolation):

```yaml
# In docker-compose.yml, replace network_mode: host with:
networks:
  - default

# And ensure CAMERA_HOST in .env uses the camera's IP address
```

### Resource Limits

Uncomment the `deploy` section in [docker-compose.yml](docker-compose.yml) to limit CPU and memory:

```yaml
deploy:
  resources:
    limits:
      cpus: '0.5'      # Max 50% of one CPU core
      memory: 256M     # Max 256MB RAM
```

### Running Multiple Cameras

To monitor multiple cameras, create separate service entries in docker-compose.yml:

```yaml
services:
  camera-front:
    build:
      context: ..
      dockerfile: examples/Dockerfile
    container_name: reolink-front
    env_file:
      - .env.front
    volumes:
      - ./recordings/front:/app/examples/recordings

  camera-back:
    build:
      context: ..
      dockerfile: examples/Dockerfile
    container_name: reolink-back
    env_file:
      - .env.back
    volumes:
      - ./recordings/back:/app/examples/recordings
```

Then create separate `.env.front` and `.env.back` files with different camera configurations.

## Security Notes

**Important:** The `.env` file contains sensitive credentials.

- Never commit `.env` to version control
- The `.env` file is already in `.gitignore`
- Only commit `.env.example` (without real credentials)
- Use strong passwords for camera access
- Consider using environment variables instead of `.env` in production

## Troubleshooting

### "Connection refused" error
- Check `CAMERA_HOST` IP address is correct
- Verify camera is on network and reachable (`ping 192.168.1.10`)
- Check `CAMERA_PORT` (default is 80, some cameras use 443 for HTTPS)

### "Invalid credentials" error
- Verify `CAMERA_USERNAME` and `CAMERA_PASSWORD` are correct
- Try logging into camera web interface with same credentials
- Some cameras require admin privileges for certain operations

### "No recordings found"
- Check that recording is enabled on camera
- Verify motion detection is enabled
- Check HDD/SD card has space and is working
- Adjust `HISTORY_HOURS` to search longer timeframe

### Real-time events not showing
- Verify motion detection is enabled
- Check sensitivity settings (may be too low)
- Ensure camera firmware supports Baichuan protocol
- Some battery cameras need to be awake for real-time events

### Baichuan connection errors
You may see errors like: `"Baichuan host X.X.X.X: lost event subscription after X.XX s"`

**This is normal and expected!** The Baichuan TCP protocol can be unstable due to:
- Network conditions (WiFi signal strength, interference)
- Camera firmware variations
- Router/firewall TCP connection timeouts

**The library handles this automatically:**
- Automatically reconnects when connection is lost
- Events continue to be received after reconnection
- No action needed from you

**To hide these errors** (recommended), set in `.env`:
```bash
BAICHUAN_LOG_LEVEL=CRITICAL
```

Other options:
- `ERROR` - Show only error messages (hides reconnection info)
- `WARNING` - Show warnings and errors
- `INFO` - Show all information (very verbose)
- `DEBUG` - Show detailed debug info (extremely verbose)

**To reduce connection issues:**
- Use wired Ethernet instead of WiFi if possible
- Check WiFi signal strength (script will display this)
- Ensure router isn't aggressively closing idle TCP connections
- Update camera firmware to latest version

### Download fails
- Check disk space in `DOWNLOAD_PATH` directory
- Verify you have write permissions to download directory
- Large recordings may take time to download

## Further Reading

- [../doc/retrieving_motion_events.md](../doc/retrieving_motion_events.md) - Detailed guide on motion event retrieval
- [../doc/baichuan_get_states.md](../doc/baichuan_get_states.md) - Deep dive into Baichuan protocol
- [../CLAUDE.md](../CLAUDE.md) - Architecture and development guide
- [../README.md](../README.md) - Main library documentation
