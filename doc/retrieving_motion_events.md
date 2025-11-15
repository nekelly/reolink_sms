# Retrieving Motion Events from Reolink Cameras

This guide explains how to retrieve motion events and recordings from Reolink cameras using the `reolink_aio` library.

## Overview

There are **three main ways** to get motion event information from Reolink cameras:

1. **Real-time event monitoring** - Subscribe to live push events via ONVIF or Baichuan TCP
2. **Current motion state** - Check if motion is currently detected
3. **Historical recordings** - Search for recorded video files triggered by motion events

## Method 1: Real-time Event Monitoring

### ONVIF Subscription (Legacy Method)

Subscribe to ONVIF events using a webhook:

```python
from reolink_aio.api import Host
import asyncio

async def monitor_events_onvif():
    # Initialize and connect
    host = Host('192.168.1.10', 'admin', 'password')
    await host.get_host_data()

    # Subscribe to ONVIF events with your webhook URL
    webhook_url = 'http://192.168.1.100:8000/webhook'
    await host.subscribe(webhook_url)

    # Keep subscription alive
    while True:
        await asyncio.sleep(300)  # Wait 5 minutes
        if host.renewtimer <= 100:
            await host.renew()  # Renew subscription before it expires

asyncio.run(monitor_events_onvif())
```

**ONVIF Events:**
- Motion detection events
- AI detection events (person, vehicle, pet, etc.)
- Doorbell press events
- Events delivered via HTTP POST to your webhook

**Limitations:**
- Requires publicly accessible webhook endpoint
- Subscription expires and needs renewal (every ~15 minutes)
- Some battery devices may not support ONVIF

### Baichuan TCP Push Events (Recommended)

Use the more efficient Baichuan TCP protocol for real-time events:

```python
from reolink_aio.api import Host
import asyncio
import logging

logging.basicConfig(level=logging.INFO)
_LOGGER = logging.getLogger(__name__)

def motion_callback(channel: int, event_type: str):
    """Called when motion event occurs"""
    _LOGGER.info(f"Motion detected on channel {channel}: {event_type}")

async def monitor_events_baichuan():
    # Initialize and connect
    host = Host('192.168.1.10', 'admin', 'password')
    await host.get_host_data()

    # Register callback for events
    host.baichuan.register_callback("my_app_id", motion_callback)

    # Subscribe to TCP push events
    await host.baichuan.subscribe_events()

    # Let it run for a while
    await asyncio.sleep(3600)  # Monitor for 1 hour

    # Cleanup
    await host.baichuan.unsubscribe_events()
    await host.logout()

asyncio.run(monitor_events_baichuan())
```

**Baichuan Push Events:**
- Motion detection
- AI detection (person, vehicle, animal, package, etc.)
- PIR sensor triggers
- Smart AI events (line crossing, intrusion, loitering)
- State changes automatically update `Host` instance

**Advantages:**
- No webhook server needed
- Persistent TCP connection (port 9000)
- Better for battery devices (see [baichuan_get_states.md](baichuan_get_states.md))
- Automatic state synchronization
- Lower latency than ONVIF

## Method 2: Current Motion State

Check if motion is **currently being detected**:

```python
from reolink_aio.api import Host
import asyncio

async def check_current_motion():
    host = Host('192.168.1.10', 'admin', 'password')
    await host.get_host_data()

    # Query current motion state
    await host.get_states()

    # Check motion state for channel 0
    channel = 0
    if host.motion_detected(channel):
        print(f"Motion is currently detected on channel {channel}")
    else:
        print(f"No motion detected on channel {channel}")

    # Get specific motion state
    motion_state = await host.get_motion_state(channel)
    print(f"Motion state: {motion_state}")

    await host.logout()

asyncio.run(check_current_motion())
```

**State Methods:**
- `host.motion_detected(channel)` - Returns `True` if motion currently detected
- `await host.get_motion_state(channel)` - Returns detailed motion state
- `await host.get_states()` - Updates all cached states including motion

**Implementation Details:**

The library uses different commands based on camera capabilities:

- **Modern cameras**: `GetEvents` command (returns motion + AI detection states)
- **Older cameras**: `GetMdState` (motion) + `GetAiState` (AI detection)

These are **non-waking commands** (see [baichuan_get_states.md](baichuan_get_states.md)) - safe to query on battery devices without draining battery.

## Method 3: Historical Motion Event Recordings

Search for **recorded video files** triggered by motion events:

### Basic VOD File Search

```python
from reolink_aio.api import Host
from datetime import datetime, timedelta
import asyncio

async def search_motion_recordings():
    host = Host('192.168.1.10', 'admin', 'password')
    await host.get_host_data()

    channel = 0

    # Search last 24 hours
    end = datetime.now()
    start = end - timedelta(hours=24)

    # Request VOD files
    status_list, vod_files = await host.request_vod_files(
        channel=channel,
        start=start,
        end=end
    )

    print(f"Found {len(vod_files)} recordings")

    for vod_file in vod_files:
        print(f"Recording: {vod_file.start_time} - {vod_file.end_time}")
        print(f"  Duration: {vod_file.duration}")
        print(f"  Size: {vod_file.size} bytes")
        print(f"  Stream: {vod_file.type}")  # 'main' or 'sub'
        if vod_file.bc_triggers:
            print(f"  Triggers: {vod_file.bc_triggers}")

    await host.logout()

asyncio.run(search_motion_recordings())
```

### Filter by Motion Trigger Type

Use `VOD_trigger` flags to filter recordings by event type:

```python
from reolink_aio.api import Host
from reolink_aio.typings import VOD_trigger
from datetime import datetime, timedelta
import asyncio

async def search_motion_only():
    host = Host('192.168.1.10', 'admin', 'password')
    await host.get_host_data()

    channel = 0
    end = datetime.now()
    start = end - timedelta(hours=24)

    # Get only MOTION-triggered recordings
    status_list, motion_recordings = await host.request_vod_files(
        channel=channel,
        start=start,
        end=end,
        trigger=VOD_trigger.MOTION
    )

    print(f"Found {len(motion_recordings)} motion-triggered recordings")

    for rec in motion_recordings:
        print(f"{rec.start_time}: Motion recording, duration {rec.duration}")

    await host.logout()

asyncio.run(search_motion_only())
```

**Available Trigger Types** ([typings.py:294-313](../reolink_aio/typings.py#L294-L313)):

```python
from reolink_aio.typings import VOD_trigger

VOD_trigger.MOTION      # General motion detection
VOD_trigger.PERSON      # AI person detection
VOD_trigger.VEHICLE     # AI vehicle detection
VOD_trigger.ANIMAL      # AI animal/pet detection
VOD_trigger.PACKAGE     # Package detection
VOD_trigger.DOORBELL    # Doorbell press
VOD_trigger.FACE        # Face detection
VOD_trigger.CRYING      # Baby cry detection
VOD_trigger.CROSSLINE   # Smart AI line crossing
VOD_trigger.INTRUSION   # Smart AI intrusion zone
VOD_trigger.LINGER      # Smart AI loitering
VOD_trigger.TIMER       # Scheduled recording
VOD_trigger.IO          # I/O trigger
VOD_trigger.FORGOTTEN_ITEM
VOD_trigger.TAKEN_ITEM
```

**Combining Triggers:**

Since `VOD_trigger` is an `IntFlag`, you can combine multiple triggers:

```python
# Get recordings triggered by MOTION OR PERSON
trigger = VOD_trigger.MOTION | VOD_trigger.PERSON
status_list, files = await host.request_vod_files(
    channel=0,
    start=start,
    end=end,
    trigger=trigger
)
```

### Search with Stream Type

Specify which video stream to search:

```python
# Search only 'main' stream (high quality)
status_list, vod_files = await host.request_vod_files(
    channel=0,
    start=start,
    end=end,
    stream='main'  # or 'sub' for lower quality
)

# Search both streams (default behavior if stream=None)
status_list, vod_files = await host.request_vod_files(
    channel=0,
    start=start,
    end=end,
    stream=None  # Returns both main and sub
)
```

### Quick Status Check (Calendar View)

Get a quick overview of which days have recordings:

```python
from datetime import datetime
import asyncio

async def check_recording_days():
    host = Host('192.168.1.10', 'admin', 'password')
    await host.get_host_data()

    # Status-only search (faster, returns calendar data)
    status_list, _ = await host.request_vod_files(
        channel=0,
        start=datetime(2024, 1, 1),
        end=datetime(2024, 12, 31),
        status_only=True  # Don't return file list, just which days have recordings
    )

    for status in status_list:
        print(f"{status.year}-{status.month}: Days with recordings: {status.days}")
        # Iterate over dates
        for date in status:
            print(f"  Recording on {date}")

    await host.logout()

asyncio.run(check_recording_days())
```

**VOD_search_status** object ([typings.py:246-292](../reolink_aio/typings.py#L246-L292)):
- `status.year` - Year
- `status.month` - Month number
- `status.days` - Tuple of day numbers with recordings
- Iterable: `for date in status` yields `datetime.date` objects
- Supports `date in status` checks

## Method 4: Download Motion Event Video

Once you have VOD files, you can get playback URLs or download them:

### Get Playback URL

```python
async def get_playback_url():
    host = Host('192.168.1.10', 'admin', 'password')
    await host.get_host_data()

    # Search for recordings
    status_list, vod_files = await host.request_vod_files(
        channel=0,
        start=start,
        end=end,
        trigger=VOD_trigger.MOTION
    )

    if vod_files:
        vod_file = vod_files[0]  # Get first recording

        # Get FLV stream URL (default)
        url, content_type = await host.get_vod_source(
            channel=0,
            filename=vod_file.file_name
        )
        print(f"Playback URL: {url}")
        print(f"Content-Type: {content_type}")

    await host.logout()
```

### Download Recording

```python
async def download_motion_video():
    host = Host('192.168.1.10', 'admin', 'password')
    await host.get_host_data()

    # Find motion recordings
    status_list, vod_files = await host.request_vod_files(
        channel=0,
        start=start,
        end=end,
        trigger=VOD_trigger.MOTION
    )

    if vod_files:
        vod_file = vod_files[0]

        # Download to file
        output_path = f"motion_{vod_file.start_time.strftime('%Y%m%d_%H%M%S')}.mp4"

        await host.download_vod_file(
            channel=0,
            filename=vod_file.file_name,
            output_path=output_path
        )

        print(f"Downloaded to {output_path}")

    await host.logout()
```

## VOD_file Object Details

The `VOD_file` object ([typings.py:339-430](../reolink_aio/typings.py#L339-L430)) provides detailed information:

```python
vod_file.start_time      # datetime: Recording start time
vod_file.end_time        # datetime: Recording end time
vod_file.playback_time   # datetime: When the event occurred
vod_file.duration        # timedelta: Recording duration
vod_file.type            # str: 'main' or 'sub' stream
vod_file.size            # int: File size in bytes
vod_file.file_name       # str: Filename for download/playback
vod_file.bc_triggers     # VOD_trigger | None: Event triggers (if available)
```

**Trigger Information:**

The `bc_triggers` attribute comes from Baichuan protocol and indicates what triggered the recording:

```python
for vod_file in vod_files:
    if vod_file.bc_triggers:
        if VOD_trigger.MOTION in vod_file.bc_triggers:
            print("Triggered by motion")
        if VOD_trigger.PERSON in vod_file.bc_triggers:
            print("Triggered by person detection")
        # Can have multiple triggers
```

## Complete Example: Motion Event Logger

Here's a complete example that monitors motion and logs events:

```python
from reolink_aio.api import Host
from reolink_aio.typings import VOD_trigger
from datetime import datetime, timedelta
import asyncio
import logging

logging.basicConfig(level=logging.INFO)
_LOGGER = logging.getLogger(__name__)

class MotionEventMonitor:
    def __init__(self, host: str, username: str, password: str):
        self.host = Host(host, username, password)
        self.motion_events = []

    async def setup(self):
        """Initialize connection"""
        await self.host.get_host_data()
        _LOGGER.info(f"Connected to {self.host.nvr_name}")
        _LOGGER.info(f"Channels: {self.host.channels}")

    async def monitor_realtime(self, duration_seconds: int):
        """Monitor real-time events via Baichuan"""
        def event_callback():
            timestamp = datetime.now()
            _LOGGER.info(f"[{timestamp}] Motion event detected!")
            self.motion_events.append(timestamp)

        # Register callback
        self.host.baichuan.register_callback("motion_monitor", event_callback)

        # Subscribe to events
        await self.host.baichuan.subscribe_events()

        _LOGGER.info(f"Monitoring for {duration_seconds} seconds...")
        await asyncio.sleep(duration_seconds)

        # Cleanup
        await self.host.baichuan.unsubscribe_events()
        _LOGGER.info(f"Detected {len(self.motion_events)} motion events")

    async def get_historical_events(self, hours: int, channel: int = 0):
        """Get motion recordings from last N hours"""
        end = datetime.now()
        start = end - timedelta(hours=hours)

        _LOGGER.info(f"Searching recordings from {start} to {end}")

        status_list, vod_files = await self.host.request_vod_files(
            channel=channel,
            start=start,
            end=end,
            trigger=VOD_trigger.MOTION
        )

        _LOGGER.info(f"Found {len(vod_files)} motion recordings")

        for vod_file in vod_files:
            _LOGGER.info(
                f"  {vod_file.start_time} - {vod_file.end_time} "
                f"({vod_file.duration}) - {vod_file.size} bytes"
            )
            if vod_file.bc_triggers:
                _LOGGER.info(f"    Triggers: {vod_file.bc_triggers}")

        return vod_files

    async def cleanup(self):
        """Cleanup connection"""
        await self.host.logout()

async def main():
    monitor = MotionEventMonitor('192.168.1.10', 'admin', 'password')

    try:
        await monitor.setup()

        # Monitor real-time for 5 minutes
        await monitor.monitor_realtime(300)

        # Get historical events from last 24 hours
        recordings = await monitor.get_historical_events(hours=24, channel=0)

    finally:
        await monitor.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
```

## Protocol Details

### How Motion Detection Works

The library uses different protocols and commands depending on the camera model:

**Modern Cameras** (with `GetEvents` support):
```python
# Single command returns all event states
body = [{"cmd": "GetEvents", "action": 0, "param": {"channel": 0}}]
# Returns: {"motion": 1, "ai": {"person": 1, "vehicle": 0, ...}}
```

**Older Cameras**:
```python
# Separate commands for motion and AI
body = [
    {"cmd": "GetMdState", "action": 0, "param": {"channel": 0}},  # Motion
    {"cmd": "GetAiState", "action": 0, "param": {"channel": 0}}   # AI detection
]
```

**Via Baichuan** ([baichuan_get_states.md](baichuan_get_states.md)):
- Command ID `GetEvents` queries current detection state
- Listed in `NONE_WAKING_COMMANDS` - won't wake battery devices
- Updates shared state cache: `host._motion_state[channel]`

### State Caching

Both HTTP and Baichuan protocols update the same state cache:

```python
# After calling get_states() (HTTP or Baichuan)
host._motion_state[channel]      # Current motion detection state
host._ai_detection_states[channel]  # AI detection states

# Accessed via getter methods
host.motion_detected(channel)    # Returns cached state
```

See [baichuan_get_states.md](baichuan_get_states.md) for details on state sharing between protocols.

## Performance Considerations

### Real-time Monitoring

**Baichuan TCP** (recommended):
- Persistent connection, instant notifications
- Minimal battery drain (events pushed, not polled)
- Best for continuous monitoring

**ONVIF Subscription**:
- Requires webhook infrastructure
- Subject to network/firewall issues
- Good for integration with home automation systems

### Historical Search

**Search Optimization**:
```python
# Fast: Status-only search (calendar view)
status_list, _ = await host.request_vod_files(
    channel=0, start=start, end=end, status_only=True
)

# Slow: Full file list with all metadata
status_list, vod_files = await host.request_vod_files(
    channel=0, start=start, end=end
)

# Fastest: Filter by trigger type (uses Baichuan optimization)
status_list, motion_only = await host.request_vod_files(
    channel=0, start=start, end=end, trigger=VOD_trigger.MOTION
)
```

**Implementation Note** ([api.py:5585-5592](../reolink_aio/api.py#L5585-L5592)):
- When `trigger` is specified, library uses `baichuan.search_vod_type()` first
- This returns recordings already filtered by trigger
- Falls back to HTTP search if Baichuan fails
- Significant performance improvement for large time ranges

## Battery Device Considerations

For battery-powered cameras:

**Non-waking Commands** (safe to call frequently):
- `GetEvents` / `GetMdState` - Check current motion state
- Won't wake device from sleep
- Query via Baichuan when device is asleep

**Waking Commands** (avoid unless necessary):
- Some VOD searches may wake device
- Use `wake` parameter in `get_states()` to control

See [baichuan_get_states.md](baichuan_get_states.md) section on "Battery Device Optimization" for details.

## Troubleshooting

### No Motion Events Received

1. **Check motion detection is enabled:**
   ```python
   await host.get_states()
   if not host.motion_detection_state(channel):
       await host.set_motion_detection(channel, True)
   ```

2. **Verify camera is online:**
   ```python
   if not host.camera_online(channel):
       print("Camera is offline")
   ```

3. **Check sensitivity settings:**
   ```python
   sensitivity = host.sensitivity(channel)
   print(f"Current sensitivity: {sensitivity}")
   ```

### Empty VOD File List

1. **Verify recordings are enabled:**
   ```python
   if not host.recording_enabled(channel):
       await host.set_recording(channel, True)
   ```

2. **Check HDD space:**
   ```python
   await host.get_host_data()
   hdd_info = host.hdd_info
   print(f"HDD: {hdd_info}")
   ```

3. **Verify time range:**
   ```python
   # Make sure start < end and they're in camera's timezone
   print(f"Camera timezone: {host.time_zone}")
   ```

## Related Documentation

- [baichuan_get_states.md](baichuan_get_states.md) - Deep dive into Baichuan protocol and state management
- [CLAUDE.md](../CLAUDE.md) - Overall architecture and development guide
- [api.py](../reolink_aio/api.py) - Source code for HTTP API methods
- [baichuan/baichuan.py](../reolink_aio/baichuan/baichuan.py) - Source code for Baichuan protocol
- [typings.py](../reolink_aio/typings.py) - Type definitions including VOD_trigger and VOD_file
