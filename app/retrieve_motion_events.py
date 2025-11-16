#!/usr/bin/env python3
"""
Retrieve motion events from Reolink camera.

This script demonstrates how to retrieve motion events from a Reolink camera
using both real-time monitoring and historical recording search.

Configuration is loaded from a .env file.
"""

import asyncio
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from time import time as get_time

# Add parent directory to path for local development
sys.path.insert(0, str(Path(__file__).parent.parent))

from reolink_aio.api import Host
from reolink_aio.typings import VOD_trigger

# Optional Twilio import
try:
    from twilio.rest import Client as TwilioClient
    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False
    TwilioClient = None

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
_LOGGER = logging.getLogger(__name__)

# Suppress verbose Twilio HTTP logging (only show on errors)
logging.getLogger('twilio.http_client').setLevel(logging.WARNING)


def load_env():
    """Load configuration from .env file"""
    env_file = Path(__file__).parent / '.env'

    if not env_file.exists():
        _LOGGER.error(f".env file not found at {env_file}")
        _LOGGER.info("Please create a .env file with the following format:")
        _LOGGER.info("CAMERA_HOST=192.168.1.10")
        _LOGGER.info("CAMERA_USERNAME=admin")
        _LOGGER.info("CAMERA_PASSWORD=yourpassword")
        _LOGGER.info("CAMERA_PORT=80")
        _LOGGER.info("CAMERA_CHANNEL=0")
        _LOGGER.info("MONITOR_DURATION=300  # seconds to monitor for real-time events")
        _LOGGER.info("HISTORY_HOURS=24      # hours to search for historical recordings")
        _LOGGER.info("DOWNLOAD_RECORDINGS=false  # whether to download recordings")
        _LOGGER.info("DOWNLOAD_PATH=./recordings  # where to save downloaded recordings")
        sys.exit(1)

    config = {}
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, value = line.split('=', 1)
                config[key.strip()] = value.strip()

    return config


def get_config_value(config, key, default=None, value_type=str):
    """Get configuration value with type conversion"""
    value = config.get(key, default)

    if value is None:
        return None

    if value_type == bool:
        return value.lower() in ('true', '1', 'yes', 'on')
    elif value_type == int:
        return int(value)
    elif value_type == float:
        return float(value)
    else:
        return value


def format_duration(seconds):
    """Format seconds into human-readable duration (days, hours, minutes, seconds)"""
    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if secs > 0 or not parts:  # Always show seconds if nothing else
        parts.append(f"{secs}s")

    return " ".join(parts)


class MotionEventRetriever:
    """Retrieves motion events from Reolink camera"""

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        port: int = 80,
        twilio_config: dict = None
    ):
        self.host_obj = Host(host, username, password, port=port)
        self.motion_events = []
        self.last_motion_state = {}

        # SMS/Twilio setup
        self.twilio_client = None
        self.twilio_from = None
        self.twilio_to = None
        self.sms_on_motion = False
        self.sms_cooldown = 300  # seconds
        self.last_sms_time = 0

        # Touchfile setup
        self.touchfile_path = None
        self.touchfile_check_interval = 5
        self.touchfile_enabled = False

        # Disk monitoring setup
        self.disk_monitor_enabled = False
        self.disk_monitor_path = '/'
        self.disk_monitor_threshold = 90
        self.disk_monitor_check_interval = 3600
        self.last_disk_alert_time = 0

        if twilio_config:
            self._setup_twilio(twilio_config)

    def _setup_twilio(self, config: dict):
        """Setup Twilio SMS client"""
        # Check if SMS is even enabled
        sms_on_motion = config.get('sms_on_motion', False)
        if not sms_on_motion:
            _LOGGER.debug("SMS notifications disabled in config (SMS_ON_MOTION=false)")
            return

        if not TWILIO_AVAILABLE:
            _LOGGER.warning("Twilio library not installed. SMS notifications disabled.")
            _LOGGER.info("Install with: pip install twilio")
            return

        account_sid = config.get('account_sid')
        auth_token = config.get('auth_token')
        from_number = config.get('from_number')
        to_number = config.get('to_number')

        if not all([account_sid, auth_token, from_number, to_number]):
            _LOGGER.warning("Twilio credentials incomplete. SMS notifications disabled.")
            _LOGGER.info("Required: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER, TWILIO_TO_NUMBER")
            return

        try:
            self.twilio_client = TwilioClient(account_sid, auth_token)
            self.twilio_from = from_number
            self.twilio_to = to_number
            self.sms_on_motion = sms_on_motion
            self.sms_cooldown = config.get('sms_cooldown', 300)

            _LOGGER.info(f"✅ Twilio SMS initialized (from {from_number} to {to_number})")
            _LOGGER.info(f"   SMS cooldown: {self.sms_cooldown} seconds")

            # Setup touchfile monitoring if configured
            touchfile_path = config.get('touchfile_path')
            if touchfile_path:
                self.touchfile_path = Path(touchfile_path)
                self.touchfile_check_interval = config.get('touchfile_check_interval', 5)
                self.touchfile_enabled = True
                _LOGGER.info(f"✅ Touchfile SMS trigger enabled: {self.touchfile_path}")
                _LOGGER.info(f"   Check interval: {self.touchfile_check_interval} seconds")

            # Setup disk monitoring if configured
            disk_monitor_enabled = config.get('disk_monitor_enabled', False)
            if disk_monitor_enabled:
                self.disk_monitor_path = config.get('disk_monitor_path', '/')
                self.disk_monitor_threshold = config.get('disk_monitor_threshold', 90)
                self.disk_monitor_check_interval = config.get('disk_monitor_check_interval', 3600)
                self.disk_monitor_enabled = True
                _LOGGER.info(f"✅ Disk space monitoring enabled: {self.disk_monitor_path}")
                _LOGGER.info(f"   Threshold: {self.disk_monitor_threshold}%")
                _LOGGER.info(f"   Check interval: {self.disk_monitor_check_interval} seconds")

        except Exception as e:
            _LOGGER.error(f"Failed to setup Twilio: {e}")
            _LOGGER.info("Check your Twilio credentials in .env file")
            self.twilio_client = None

    def send_sms(self, message: str, force: bool = False):
        """Send SMS via Twilio with cooldown protection"""
        if not self.twilio_client:
            return False

        # Check cooldown
        current_time = get_time()
        if not force and (current_time - self.last_sms_time) < self.sms_cooldown:
            remaining = int(self.sms_cooldown - (current_time - self.last_sms_time))
            _LOGGER.debug(f"SMS cooldown active, {remaining}s remaining")
            return False

        try:
            result = self.twilio_client.messages.create(
                body=message,
                from_=self.twilio_from,
                to=self.twilio_to
            )
            self.last_sms_time = current_time
            _LOGGER.info(f"SMS sent: {message[:50]}... (SID: {result.sid})")
            return True
        except Exception as e:
            _LOGGER.error(f"Failed to send SMS: {e}")
            _LOGGER.error(f"  Message: {message[:100]}")
            _LOGGER.error(f"  From: {self.twilio_from}")
            _LOGGER.error(f"  To: {self.twilio_to}")
            _LOGGER.error(f"  Exception type: {type(e).__name__}")

            # Log specific Twilio error details if available
            if hasattr(e, 'code'):
                _LOGGER.error(f"  Twilio error code: {e.code}")
            if hasattr(e, 'status'):
                _LOGGER.error(f"  HTTP status: {e.status}")
            if hasattr(e, 'msg'):
                _LOGGER.error(f"  Error message: {e.msg}")

            return False

    async def send_sms_async(self, message: str, force: bool = False):
        """Async wrapper for send_sms to avoid blocking the event loop"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.send_sms, message, force)

    async def _send_motion_sms(self, message: str):
        """Helper to send motion detection SMS without blocking"""
        try:
            if await self.send_sms_async(message):
                _LOGGER.info(f"📱 SMS alert sent to {self.twilio_to}")
            else:
                _LOGGER.debug("SMS not sent (cooldown active or failed)")
        except Exception as e:
            _LOGGER.error(f"Error sending motion SMS: {e}")

    async def check_touchfile(self):
        """Check for touchfile and send SMS if found"""
        if not self.touchfile_enabled or not self.touchfile_path:
            return

        try:
            if self.touchfile_path.exists():
                _LOGGER.info(f"Touchfile detected: {self.touchfile_path}")

                # Read message from file if it has content, otherwise use default
                try:
                    message_content = self.touchfile_path.read_text().strip()
                    if message_content:
                        message = message_content
                    else:
                        message = f"🔔 Manual alert triggered at {datetime.now().strftime('%H:%M:%S')}"
                except Exception as e:
                    _LOGGER.warning(f"Could not read touchfile content: {e}, using default message")
                    message = f"🔔 Manual alert triggered at {datetime.now().strftime('%H:%M:%S')}"

                # Send SMS (force=True to bypass cooldown for manual triggers)
                if await self.send_sms_async(message, force=True):
                    _LOGGER.info(f"📱 Touchfile SMS sent to {self.twilio_to}")
                else:
                    _LOGGER.warning("Failed to send touchfile SMS")

                # Delete the touchfile after processing
                try:
                    self.touchfile_path.unlink()
                    _LOGGER.debug(f"Touchfile deleted: {self.touchfile_path}")
                except Exception as e:
                    _LOGGER.warning(f"Could not delete touchfile: {e}")

        except Exception as e:
            _LOGGER.error(f"Error checking touchfile: {e}")

    async def check_disk_space(self):
        """Check disk space and send SMS if threshold exceeded"""
        if not self.disk_monitor_enabled:
            return

        try:
            import shutil

            # Get disk usage statistics
            usage = shutil.disk_usage(self.disk_monitor_path)
            percent_used = (usage.used / usage.total) * 100
            percent_free = (usage.free / usage.total) * 100

            _LOGGER.debug(f"Disk {self.disk_monitor_path}: {percent_used:.1f}% used, {percent_free:.1f}% free")

            # Check if threshold exceeded
            if percent_used >= self.disk_monitor_threshold:
                # Check cooldown (use SMS cooldown to avoid spam)
                current_time = get_time()
                if (current_time - self.last_disk_alert_time) < self.sms_cooldown:
                    remaining = int(self.sms_cooldown - (current_time - self.last_disk_alert_time))
                    _LOGGER.debug(f"Disk alert cooldown active, {remaining}s remaining")
                    return

                # Format sizes for human readability
                used_gb = usage.used / (1024**3)
                total_gb = usage.total / (1024**3)
                free_gb = usage.free / (1024**3)

                message = (
                    f"⚠️ Disk space alert: {self.disk_monitor_path}\n"
                    f"{percent_used:.1f}% used ({used_gb:.1f}GB / {total_gb:.1f}GB)\n"
                    f"{free_gb:.1f}GB free remaining"
                )

                if await self.send_sms_async(message, force=False):
                    _LOGGER.warning(f"Disk space alert sent: {percent_used:.1f}% used on {self.disk_monitor_path}")
                    self.last_disk_alert_time = current_time
                else:
                    _LOGGER.warning(f"Failed to send disk space alert (cooldown or error)")

        except Exception as e:
            _LOGGER.error(f"Error checking disk space: {e}")

    async def setup(self):
        """Initialize connection and get camera info"""
        _LOGGER.info("Connecting to camera...")
        await self.host_obj.get_host_data()

        _LOGGER.info(f"Connected to: {self.host_obj.nvr_name}")
        _LOGGER.info(f"Model: {self.host_obj.model}")
        _LOGGER.info(f"Firmware: {self.host_obj.sw_version}")
        _LOGGER.info(f"Channels: {self.host_obj.channels}")
        _LOGGER.info(f"Is NVR: {self.host_obj.is_nvr}")

        # Get initial states
        await self.host_obj.get_states()

        # Check WiFi signal if applicable
        if self.host_obj.wifi_connection:
            wifi_signal = self.host_obj.wifi_signal()
            _LOGGER.info(f"WiFi signal strength: {wifi_signal}%")
            if wifi_signal and wifi_signal < 50:
                _LOGGER.warning(f"Weak WiFi signal ({wifi_signal}%) may cause connection issues")

    async def check_motion_detection_enabled(self, channel: int):
        """Check if motion detection is enabled on the channel"""
        # Check if motion detection settings exist
        if not hasattr(self.host_obj, '_md_alarm_settings') or channel not in self.host_obj._md_alarm_settings:
            _LOGGER.warning(f"Motion detection settings not available for channel {channel}")
            _LOGGER.info("This may be a camera that uses PIR detection instead")
            return False

        # Check if motion detection is enabled
        md_settings = self.host_obj._md_alarm_settings[channel]
        if "Alarm" in md_settings:
            is_enabled = md_settings["Alarm"].get("enable", 0) == 1
        elif "MdAlarm" in md_settings:
            is_enabled = md_settings["MdAlarm"].get("enable", 0) == 1
        else:
            _LOGGER.warning(f"Unknown motion detection settings structure for channel {channel}")
            return False

        if not is_enabled:
            _LOGGER.warning(f"Motion detection is DISABLED on channel {channel}")
            _LOGGER.info("Attempting to enable motion detection via API...")
            _LOGGER.debug(f"Current motion detection settings: {md_settings}")

            try:
                # Make a deep copy to avoid modifying cached settings
                import copy
                settings_copy = copy.deepcopy(md_settings)

                # Handle both "Alarm" and "MdAlarm" structure variations
                # We need to send the FULL structure back with enable=1
                if "Alarm" in settings_copy:
                    settings_copy["Alarm"]["enable"] = 1
                    _LOGGER.debug("Using 'Alarm' structure")
                elif "MdAlarm" in settings_copy:
                    # Add enable field to the MdAlarm object (keep all other fields)
                    settings_copy["MdAlarm"]["enable"] = 1
                    _LOGGER.debug("Using 'MdAlarm' structure with full settings")

                body = [{"cmd": "SetAlarm", "action": 0, "param": settings_copy}]
                _LOGGER.debug(f"Sending SetAlarm with enable=1 and complete structure")

                await self.host_obj.send_setting(body)
                # Refresh settings to verify
                await self.host_obj.get_states()
                _LOGGER.info("✓ Motion detection enabled successfully")
            except Exception as e:
                _LOGGER.error(f"Failed to enable motion detection: {e}")
                _LOGGER.warning("Please enable motion detection manually in camera settings")
                return False

        _LOGGER.info(f"Motion detection is enabled on channel {channel}")
        sensitivity = self.host_obj.md_sensitivity(channel)
        _LOGGER.info(f"Motion sensitivity level: {sensitivity}")
        return True

    async def check_recording_enabled(self, channel: int):
        """Check if recording is enabled on the channel"""
        try:
            is_enabled = self.host_obj.recording_enabled(channel)
        except (KeyError, AttributeError) as e:
            _LOGGER.warning(f"Unable to determine recording status for channel {channel}: {e}")
            _LOGGER.info("Recording status check skipped - will assume it's enabled")
            return True  # Assume enabled to continue with the script

        if not is_enabled:
            _LOGGER.warning(f"Recording is DISABLED on channel {channel}")
            return False

        _LOGGER.info(f"Recording is enabled on channel {channel}")
        return True

    async def monitor_realtime(self, duration_seconds: int, channel: int = 0):
        """Monitor real-time motion events via Baichuan TCP"""
        if duration_seconds == 0:
            _LOGGER.info("Starting INFINITE real-time event monitoring...")
            _LOGGER.info("Press Ctrl+C to stop")
        else:
            _LOGGER.info(f"Starting real-time event monitoring for {duration_seconds} seconds...")
        _LOGGER.info("Note: Connection errors are normal - the library automatically reconnects")

        def event_callback():
            """Called when any event occurs"""
            _LOGGER.debug("event_callback() called")
            timestamp = datetime.now()

            # Check if motion state changed
            try:
                _LOGGER.debug("Checking motion_detected()...")
                motion_now = self.host_obj.motion_detected(channel)
                _LOGGER.debug(f"motion_detected() returned: {motion_now}")
            except Exception as e:
                _LOGGER.error(f"Error checking motion state: {e}")
                return

            was_motion = self.last_motion_state.get(channel, False)
            _LOGGER.debug(f"Motion state: was={was_motion}, now={motion_now}")

            if motion_now and not was_motion:
                _LOGGER.info(f"[{timestamp}] ⚡ MOTION STARTED on channel {channel}")
                self.motion_events.append({
                    'timestamp': timestamp,
                    'channel': channel,
                    'type': 'motion_start'
                })

                # Send SMS notification if enabled
                if self.sms_on_motion:
                    _LOGGER.debug("Preparing SMS alert...")
                    camera_name = self.host_obj.camera_name(channel)
                    _LOGGER.debug(f"Camera name: {camera_name}")

                    sms_message = (
                        f"🚨 Motion detected on {camera_name} at {timestamp.strftime('%H:%M:%S')}"
                    )

                    # Schedule async SMS send as a task to avoid blocking
                    _LOGGER.debug("Scheduling SMS send task...")
                    asyncio.create_task(self._send_motion_sms(sms_message))
                    _LOGGER.debug("SMS task scheduled")

            elif not motion_now and was_motion:
                _LOGGER.info(f"[{timestamp}] ✓ MOTION ENDED on channel {channel}")
                self.motion_events.append({
                    'timestamp': timestamp,
                    'channel': channel,
                    'type': 'motion_end'
                })

            self.last_motion_state[channel] = motion_now
            _LOGGER.debug("event_callback() completed")

        # Register callback
        self.host_obj.baichuan.register_callback("motion_monitor", event_callback)

        # Subscribe to TCP push events
        try:
            await self.host_obj.baichuan.subscribe_events()
        except Exception as e:
            _LOGGER.error(f"Failed to subscribe to events: {e}")
            _LOGGER.info("Real-time monitoring will not work, but historical search will continue")
            return []

        # Monitor for specified duration
        _LOGGER.info("Monitoring active. Press Ctrl+C to stop.")

        try:
            # Check connection status periodically
            check_interval = 60  # seconds
            elapsed = 0
            infinite_mode = (duration_seconds == 0)

            # Determine touchfile check interval (use smaller interval for more responsive checks)
            touchfile_interval = self.touchfile_check_interval if self.touchfile_enabled else check_interval
            next_touchfile_check = 0
            next_status_log = check_interval
            next_motion_poll = 10  # Check motion state every 10 seconds
            next_disk_check = 0  # Check disk space immediately on start

            while infinite_mode or elapsed < duration_seconds:
                # Sleep in small increments to allow responsive touchfile checking
                sleep_time = min(touchfile_interval, 1) if self.touchfile_enabled else check_interval
                if not infinite_mode:
                    sleep_time = min(sleep_time, duration_seconds - elapsed)

                await asyncio.sleep(sleep_time)
                elapsed += sleep_time

                # Check touchfile if enabled and interval reached
                if self.touchfile_enabled and elapsed >= next_touchfile_check:
                    await self.check_touchfile()
                    next_touchfile_check = elapsed + touchfile_interval

                # Manually check motion state to catch missed callbacks
                # This handles cases where the Baichuan callback doesn't fire for motion end
                if elapsed >= next_motion_poll:
                    try:
                        event_callback()
                    except Exception as e:
                        _LOGGER.error(f"Error in motion poll callback: {e}")
                    next_motion_poll = elapsed + 10  # Next check in 10 seconds

                # Check disk space if enabled and interval reached
                if self.disk_monitor_enabled and elapsed >= next_disk_check:
                    await self.check_disk_space()
                    next_disk_check = elapsed + self.disk_monitor_check_interval

                # Log progress at regular intervals
                if elapsed >= next_status_log:
                    if infinite_mode:
                        _LOGGER.info(f"Still monitoring... running for {format_duration(elapsed)}, "
                                   f"{len(self.motion_events)} events detected so far")
                    else:
                        remaining = duration_seconds - elapsed
                        if remaining > 0:
                            _LOGGER.info(f"Still monitoring... {format_duration(remaining)} remaining, "
                                       f"{len(self.motion_events)} events detected so far")
                    next_status_log = elapsed + check_interval

        except KeyboardInterrupt:
            _LOGGER.info("Monitoring interrupted by user")

        # Cleanup
        try:
            await self.host_obj.baichuan.unsubscribe_events()
        except Exception as e:
            _LOGGER.debug(f"Error during unsubscribe (can be ignored): {e}")

        _LOGGER.info(f"Real-time monitoring complete. Detected {len(self.motion_events)} events")

        return self.motion_events

    async def get_historical_recordings(
        self,
        channel: int,
        hours: int,
        trigger_filter: VOD_trigger = VOD_trigger.MOTION
    ):
        """Get historical motion recordings"""
        end = datetime.now()
        start = end - timedelta(hours=hours)

        _LOGGER.info(f"Searching for recordings from {start.strftime('%Y-%m-%d %H:%M:%S')} "
                    f"to {end.strftime('%Y-%m-%d %H:%M:%S')}")
        _LOGGER.info(f"Filter: {trigger_filter}")

        try:
            status_list, vod_files = await self.host_obj.request_vod_files(
                channel=channel,
                start=start,
                end=end,
                trigger=trigger_filter
            )
        except Exception as e:
            _LOGGER.error(f"Error searching recordings: {e}")
            return []

        _LOGGER.info(f"Found {len(vod_files)} recordings")

        # Log details about each recording
        for i, vod_file in enumerate(vod_files, 1):
            _LOGGER.info(f"\nRecording #{i}:")
            _LOGGER.info(f"  Start: {vod_file.start_time}")
            _LOGGER.info(f"  End: {vod_file.end_time}")
            _LOGGER.info(f"  Duration: {vod_file.duration}")
            _LOGGER.info(f"  Size: {vod_file.size:,} bytes ({vod_file.size / 1024 / 1024:.2f} MB)")
            _LOGGER.info(f"  Stream: {vod_file.type}")
            _LOGGER.info(f"  Filename: {vod_file.file_name}")

            if vod_file.bc_triggers:
                triggers = []
                if VOD_trigger.MOTION in vod_file.bc_triggers:
                    triggers.append("Motion")
                if VOD_trigger.PERSON in vod_file.bc_triggers:
                    triggers.append("Person")
                if VOD_trigger.VEHICLE in vod_file.bc_triggers:
                    triggers.append("Vehicle")
                if VOD_trigger.ANIMAL in vod_file.bc_triggers:
                    triggers.append("Animal")
                if VOD_trigger.PACKAGE in vod_file.bc_triggers:
                    triggers.append("Package")
                if VOD_trigger.DOORBELL in vod_file.bc_triggers:
                    triggers.append("Doorbell")

                _LOGGER.info(f"  Triggers: {', '.join(triggers)}")

        return vod_files

    async def download_recording(self, channel: int, vod_file, output_dir: Path):
        """Download a single recording"""
        output_dir.mkdir(parents=True, exist_ok=True)

        # Create filename from timestamp and triggers
        timestamp_str = vod_file.start_time.strftime('%Y%m%d_%H%M%S')

        trigger_str = "recording"
        if vod_file.bc_triggers:
            if VOD_trigger.MOTION in vod_file.bc_triggers:
                trigger_str = "motion"
            if VOD_trigger.PERSON in vod_file.bc_triggers:
                trigger_str = "person"
            if VOD_trigger.VEHICLE in vod_file.bc_triggers:
                trigger_str = "vehicle"

        filename = f"{timestamp_str}_{trigger_str}_ch{channel}.mp4"
        output_path = output_dir / filename

        _LOGGER.info(f"Downloading to {output_path}...")

        try:
            await self.host_obj.download_vod_file(
                channel=channel,
                filename=vod_file.file_name,
                output_path=str(output_path)
            )
            _LOGGER.info(f"✓ Downloaded: {output_path}")
            return output_path
        except Exception as e:
            _LOGGER.error(f"✗ Failed to download: {e}")
            return None

    async def get_recording_calendar(self, channel: int, months: int = 3):
        """Get a calendar view of which days have recordings"""
        end = datetime.now()
        start = end - timedelta(days=months * 31)  # Approximate

        _LOGGER.info(f"Getting recording calendar for last {months} months...")

        try:
            status_list, _ = await self.host_obj.request_vod_files(
                channel=channel,
                start=start,
                end=end,
                status_only=True  # Fast, only returns calendar data
            )
        except Exception as e:
            _LOGGER.error(f"Error getting calendar: {e}")
            return

        _LOGGER.info("\nRecording Calendar:")
        for status in status_list:
            if len(status.days) > 0:
                _LOGGER.info(f"{status.year}-{status.month:02d}: {len(status.days)} days with recordings")
                _LOGGER.info(f"  Days: {', '.join(str(d) for d in status.days)}")

    async def cleanup(self):
        """Cleanup connection"""
        _LOGGER.info("Disconnecting from camera...")
        await self.host_obj.logout()


async def main():
    """Main function"""
    # Load configuration
    config = load_env()

    # Configure logging level from config
    log_level_str = get_config_value(config, 'LOG_LEVEL', 'INFO', str).upper()
    level_map = {
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR,
        'CRITICAL': logging.CRITICAL
    }
    if log_level_str in level_map:
        logging.getLogger().setLevel(level_map[log_level_str])
        _LOGGER.setLevel(level_map[log_level_str])
        _LOGGER.info(f"Log level set to: {log_level_str}")
    else:
        _LOGGER.warning(f"Invalid LOG_LEVEL '{log_level_str}', using INFO")

    # Parse configuration
    host = get_config_value(config, 'CAMERA_HOST', '192.168.1.10')
    username = get_config_value(config, 'CAMERA_USERNAME', 'admin')
    password = get_config_value(config, 'CAMERA_PASSWORD')
    port = get_config_value(config, 'CAMERA_PORT', 80, int)
    channel = get_config_value(config, 'CAMERA_CHANNEL', 0, int)
    monitor_duration = get_config_value(config, 'MONITOR_DURATION', 300, int)
    history_hours = get_config_value(config, 'HISTORY_HOURS', 24, int)
    download_recordings = get_config_value(config, 'DOWNLOAD_RECORDINGS', False, bool)
    download_path = Path(get_config_value(config, 'DOWNLOAD_PATH', './recordings'))
    baichuan_log_level = get_config_value(config, 'BAICHUAN_LOG_LEVEL', 'CRITICAL', str).upper()

    # Twilio SMS configuration
    twilio_config = {
        'account_sid': get_config_value(config, 'TWILIO_ACCOUNT_SID', ''),
        'auth_token': get_config_value(config, 'TWILIO_AUTH_TOKEN', ''),
        'from_number': get_config_value(config, 'TWILIO_FROM_NUMBER', ''),
        'to_number': get_config_value(config, 'TWILIO_TO_NUMBER', ''),
        'sms_on_motion': get_config_value(config, 'SMS_ON_MOTION', False, bool),
        'sms_cooldown': get_config_value(config, 'SMS_COOLDOWN', 300, int),
        'touchfile_path': get_config_value(config, 'TOUCHFILE_PATH', ''),
        'touchfile_check_interval': get_config_value(config, 'TOUCHFILE_CHECK_INTERVAL', 5, int),
        'disk_monitor_enabled': get_config_value(config, 'DISK_MONITOR_ENABLED', False, bool),
        'disk_monitor_path': get_config_value(config, 'DISK_MONITOR_PATH', '/'),
        'disk_monitor_threshold': get_config_value(config, 'DISK_MONITOR_THRESHOLD', 90, int),
        'disk_monitor_check_interval': get_config_value(config, 'DISK_MONITOR_CHECK_INTERVAL', 3600, int),
    }

    # Configure Baichuan logging level
    # This suppresses noisy connection error logs which are normal and handled automatically
    level_map = {
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR,
        'CRITICAL': logging.CRITICAL
    }
    if baichuan_log_level in level_map:
        logging.getLogger('reolink_aio.baichuan.baichuan').setLevel(level_map[baichuan_log_level])
        _LOGGER.debug(f"Baichuan logging level set to: {baichuan_log_level}")
    else:
        _LOGGER.warning(f"Invalid BAICHUAN_LOG_LEVEL '{baichuan_log_level}', using CRITICAL")
        logging.getLogger('reolink_aio.baichuan.baichuan').setLevel(logging.CRITICAL)

    if not password:
        _LOGGER.error("CAMERA_PASSWORD is required in .env file")
        sys.exit(1)

    _LOGGER.info("=" * 60)
    _LOGGER.info("Reolink Motion Event Retriever")
    _LOGGER.info("=" * 60)

    # Show SMS configuration status
    if twilio_config.get('account_sid') and twilio_config.get('sms_on_motion'):
        _LOGGER.info(f"SMS notifications: ENABLED (to {twilio_config.get('to_number')})")
    else:
        _LOGGER.info("SMS notifications: DISABLED")

    retriever = MotionEventRetriever(host, username, password, port, twilio_config=twilio_config)

    try:
        # Setup connection
        await retriever.setup()

        # Check camera settings
        _LOGGER.info("\n" + "=" * 60)
        _LOGGER.info("Camera Settings Check")
        _LOGGER.info("=" * 60)
        await retriever.check_motion_detection_enabled(channel)
        await retriever.check_recording_enabled(channel)

        # Get recording calendar
        _LOGGER.info("\n" + "=" * 60)
        _LOGGER.info("Recording Calendar")
        _LOGGER.info("=" * 60)
        await retriever.get_recording_calendar(channel, months=3)

        # Get historical recordings
        _LOGGER.info("\n" + "=" * 60)
        _LOGGER.info(f"Historical Recordings (Last {history_hours} hours)")
        _LOGGER.info("=" * 60)
        vod_files = await retriever.get_historical_recordings(
            channel=channel,
            hours=history_hours,
            trigger_filter=VOD_trigger.MOTION | VOD_trigger.PERSON | VOD_trigger.VEHICLE
        )

        # Download recordings if enabled
        if download_recordings and vod_files:
            _LOGGER.info("\n" + "=" * 60)
            _LOGGER.info("Downloading Recordings")
            _LOGGER.info("=" * 60)

            # Limit downloads to avoid filling disk
            max_downloads = 5
            _LOGGER.info(f"Downloading up to {max_downloads} recordings...")

            for vod_file in vod_files[:max_downloads]:
                await retriever.download_recording(channel, vod_file, download_path)

        # Monitor real-time events
        _LOGGER.info("\n" + "=" * 60)
        _LOGGER.info("Real-time Event Monitoring")
        _LOGGER.info("=" * 60)
        events = await retriever.monitor_realtime(
            duration_seconds=monitor_duration,
            channel=channel
        )

        # Summary
        _LOGGER.info("\n" + "=" * 60)
        _LOGGER.info("Summary")
        _LOGGER.info("=" * 60)
        _LOGGER.info(f"Historical recordings found: {len(vod_files)}")
        _LOGGER.info(f"Real-time events detected: {len(events)}")

        if events:
            motion_starts = sum(1 for e in events if e['type'] == 'motion_start')
            _LOGGER.info(f"  Motion events: {motion_starts}")

    except KeyboardInterrupt:
        _LOGGER.info("\nInterrupted by user")
    except Exception as e:
        _LOGGER.error(f"Error: {e}", exc_info=True)
    finally:
        await retriever.cleanup()

    _LOGGER.info("\nDone!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        _LOGGER.info("Exiting")
