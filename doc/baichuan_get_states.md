# Baichuan `get_states()` Method - Technical Deep Dive

## Overview

The Baichuan `get_states()` method is a sophisticated state-polling mechanism that runs in parallel with the HTTP API's `get_states()` but uses the TCP-based Baichuan protocol instead of HTTP. This document explains its architecture, purpose, and how it differs from the HTTP implementation.

## Purpose

The Baichuan version exists to:

1. **Query battery-powered devices without waking them** - Uses non-waking commands to check state while device sleeps
2. **Use more efficient TCP protocol** - Binary protocol with lower overhead than HTTP
3. **Support Baichuan-specific features** - Some features only available via TCP protocol
4. **Real-time event integration** - Leverages existing TCP connection used for push events

## Method Signature

```python
async def get_states(
    self,
    cmd_list: cmd_list_type = None,
    wake: dict[int, bool] | None = None
) -> None:
```

**Parameters:**
- `cmd_list` - Optional filter to only query specific commands/channels
  - Format: `{"GetZoomFocus": {None: 6, 1: 3}, "GetHddInfo": {None: 1}}`
  - `None` key = host-level command, numeric keys = channel numbers
- `wake` - Dict mapping channels to wake status
  - `True` = device is awake or should be woken
  - `False` = device is asleep, only query non-waking commands

## Architecture

### Parallel Coroutine Execution

The method uses `asyncio.gather()` to execute all state queries **in parallel**:

```python
coroutines: list[Coroutine] = []
# Build list of state-fetching coroutines based on capabilities
coroutines.append(self.get_scene())
coroutines.append(self.get_wifi_signal(channel))
# ... many more

# Execute all in parallel with 90-second timeout (3 * TIMEOUT)
async with asyncio.timeout(3 * TIMEOUT):
    results = await asyncio.gather(*coroutines, return_exceptions=True)
```

This is much faster than sequential polling and efficiently uses the TCP connection.

### Smart Wake Management

The method implements **intelligent battery-aware logic** to avoid draining battery devices:

#### Helper Functions

```python
def inc_host_cmd(cmd: str, no_wake_check=False) -> bool:
    """Include host-level command if in cmd_list AND (awake OR non-waking)"""
    return (cmd in cmd_list or not cmd_list) and \
           (no_wake_check or (all_wake or not any_battery or cmd in NONE_WAKING_COMMANDS))

def inc_cmd(cmd: str, channel: int) -> bool:
    """Include channel command if in cmd_list AND (awake OR non-waking OR not battery)"""
    return (channel in cmd_list.get(cmd, []) or not cmd_list) and \
           (wake[channel] or cmd in NONE_WAKING_COMMANDS or not self.http_api.supported(channel, "battery"))
```

These determine whether to include each command based on:
- Is it in the requested `cmd_list`?
- Is the device/channel awake?
- Is it a `NONE_WAKING_COMMAND`? (defined in [const.py](../reolink_aio/const.py))
- Is it battery-powered?

#### Wake Command Categories

Commands are categorized in [const.py](../reolink_aio/const.py):

**WAKING_COMMANDS** (require device wake-up):
- `GetEnc`, `GetWhiteLed`, `GetZoomFocus`, `GetAudioCfg`
- `GetPtzGuard`, `GetAiCfg`, `GetAiAlarm`, `GetPtzCurPos`
- `GetDingDongCfg`, `GetPerformance`, `GetMask`
- Numeric IDs: `296`, `483`

**NONE_WAKING_COMMANDS** (can query while asleep):
- `GetIsp`, `GetEvents`, `GetMdState`, `GetAiState`
- `GetIrLights`, `GetBatteryInfo`, `GetPirInfo`, `GetPowerLed`
- `GetImage`, `GetEmail`, `GetPush`, `GetFtp`, `GetRec`
- `GetHddInfo`, `GetChannelstatus`, `GetScene`
- Numeric IDs: `115`, `208`, `594`

## Queried States

### Host-Level Queries

```python
# Scene settings (indoor/outdoor profiles)
if self.supported(None, "scenes") and inc_host_cmd("GetScene"):
    coroutines.append(self.get_scene())

# WiFi signal strength
if self.http_api.supported(None, "wifi") and inc_host_cmd("115"):
    coroutines.append(self.get_wifi_signal())

# Doorbell chime discovery (always included, non-waking)
if self.supported(None, "chime"):
    coroutines.append(self.GetDingDongList())

# Chime configuration
if self.supported(None, "chime") and inc_host_cmd("GetDingDongCfg", no_wake_check=True):
    coroutines.append(self.GetDingDongCfg())
```

### Per-Channel Queries

For each online channel:

```python
for channel in self.http_api._channels:
    if not self.http_api.camera_online(channel):
        continue

    # WiFi signal (per-channel for NVR-connected cameras)
    if self.http_api.supported(channel, "wifi") and inc_cmd("115", channel):
        coroutines.append(self.get_wifi_signal(channel))

    # Smart AI detection rules (intrusion, line crossing, loitering)
    if self.supported(channel, "rules"):
        coroutines.append(self.get_rule_ids(channel))
        if inc_cmd("rules", channel):
            for rule_id in self.rule_ids(channel):
                coroutines.append(self.get_rule(rule_id, channel))

    # Day/Night state (Color/Black&White mode)
    if self.supported(channel, "day_night_state") and inc_cmd("296", channel):
        coroutines.append(self.get_day_night_state(channel))

    # Doorbell chime configuration
    if self.http_api.supported(channel, "chime") and inc_cmd("GetDingDongCfg", channel):
        coroutines.append(self.GetDingDongCfg(channel))

    # Hardwired chime (only if not cached - can cause physical rattle)
    if self.supported(channel, "hardwired_chime") and \
       channel in cmd_list.get("483", []) and \
       channel not in self._hardwired_chime_settings:
        coroutines.append(self.get_ding_dong_ctrl(channel))

    # IR LED brightness/status
    if self.supported(channel, "ir_brightness") and inc_cmd("208", channel):
        coroutines.append(self.get_status_led(channel))

    # Floodlight color temperature (white LED)
    if self.supported(channel, "color_temp") and inc_cmd("GetWhiteLed", channel):
        coroutines.append(self.get_floodlight(channel))

    # Baby cry detection sensitivity
    if self.supported(channel, "ai_cry") and inc_cmd("299", channel):
        coroutines.append(self.get_cry_detection(channel))

    # YOLO AI detection settings (person, vehicle, animal, package)
    if self.supported(channel, "ai_yolo") and inc_cmd("GetAiAlarm", channel):
        coroutines.append(self.get_yolo_settings(channel))

    # PIR (Passive Infrared) sensor info
    if self.http_api.supported(channel, "PIR") and inc_cmd("GetPirInfo", channel):
        coroutines.append(self.GetPirInfo(channel))

    # PTZ (Pan-Tilt-Zoom) current position
    if self.supported(channel, "ptz_position") and inc_cmd("GetPtzCurPos", channel):
        coroutines.append(self.get_ptz_position(channel))

    # Pre-recording buffer settings
    if self.supported(channel, "pre_record") and inc_cmd("594", channel):
        coroutines.append(self.get_pre_recording(channel))

    # Audio volume settings
    if self.supported(channel, "volume") and inc_cmd("GetAudioCfg", channel):
        coroutines.append(self.GetAudioCfg(channel))

    # Audio noise reduction
    if self.supported(channel, "noise_reduction") and inc_cmd("439", channel):
        coroutines.append(self.GetAudioNoise(channel))
```

### Chime-Specific Queries

```python
for chime_id, chime in self.http_api._chime_list.items():
    if not chime.online:
        continue

    # Silent mode status
    if inc_ch_wake_cmd("609", chime.channel):
        coroutines.append(self.get_ding_dong_silent(channel=chime.channel, chime_id=chime_id))

    # Chime options (non-waking for Hub-connected)
    if inc_host_cmd("DingDongOpt", no_wake_check=True) and chime.channel is not None:
        coroutines.append(self.get_DingDongOpt(chime_id=chime_id))
```

## Comparison: HTTP vs Baichuan `get_states()`

| Aspect | HTTP API ([api.py:2171](../reolink_aio/api.py#L2171)) | Baichuan ([baichuan.py:1409](../reolink_aio/baichuan/baichuan.py#L1409)) |
|--------|------------|----------|
| **Protocol** | HTTP POST with JSON | Binary TCP with XML responses |
| **Connection** | New connection per request (or connection pooling) | Persistent TCP connection |
| **Batching** | Bundles multiple commands in single HTTP request body | Individual TCP messages per command |
| **Encryption** | HTTPS optional (TLS) | Custom Baichuan encryption (XOR + AES) |
| **Data Format** | JSON requests/responses | XML responses parsed manually |
| **Command IDs** | Named commands like "GetIsp" | Numeric IDs like `115`, `296`, `433` |
| **Timeout** | 30 seconds default | 90 seconds (3 × TIMEOUT) |
| **Error Handling** | HTTP status codes + JSON error codes | TCP connection errors + XML parsing |
| **Port** | 80/443 (HTTP/HTTPS) | 9000 (Baichuan) |
| **Use Case** | General API access, one-off commands | Continuous monitoring, battery devices, push events |

## Baichuan TCP Protocol

### The `@http_cmd` Decorator

Baichuan methods use a clever decorator to map HTTP command names to TCP command IDs:

```python
@http_cmd("GetNetPort")
async def get_ports(self, **_kwargs) -> dict[str, dict[str, int | bool]]:
    mess = await self.send(cmd_id=37)  # Sends Baichuan TCP command #37
    root = XML.fromstring(mess)
    # Parse XML and return data
```

This allows:
- Same capability detection logic as HTTP API
- Clear mapping between HTTP and Baichuan commands
- Protocol fallback mechanisms

### Communication Flow

The Baichuan protocol ([baichuan.py:200-240](../reolink_aio/baichuan/baichuan.py#L200-L240)) works as follows:

```
1. Binary Header:
   - Magic bytes: f0debc0a
   - Command ID (4 bytes, little-endian)
   - Message length (4 bytes, little-endian)
   - Message ID / channel (4 bytes)
   - Payload offset (4 bytes)

2. XML Extension (if channel specified):
   <Extension><channelId>0</channelId></Extension>

3. XML Body:
   Command-specific XML payload

4. Encryption:
   - XOR cipher (EncType.BC): Custom XOR with XML_KEY
   - AES (EncType.AES): AES encryption with IV

5. Response:
   - Same binary header format
   - Encrypted XML payload
   - Decrypted and parsed to extract values
```

### Example: WiFi Signal Query

```python
async def get_wifi_signal(self, channel: int | None = None) -> None:
    """Get the wifi signal of the host"""
    # Send TCP command #115 with channel
    mess = await self.send(cmd_id=115, channel=channel)

    # Parse XML response
    root = XML.fromstring(mess)
    value = self._get_value_from_xml_element(root, "signal")

    # Update shared state cache (shared with HTTP API)
    if value is not None:
        self.http_api._wifi_signal[channel] = int(value)
```

**Message Flow:**
```
Client → Server: Binary header + <Extension><channelId>0</channelId></Extension>
Server → Client: Binary header + <wifi><signal>75</signal></wifi>
Result: self.http_api._wifi_signal[0] = 75
```

## State Sharing Between Protocols

**Critical Design Principle:** Baichuan updates the **same state cache** as HTTP API.

Both protocols write to shared `Host` instance variables:

```python
# Baichuan updates HTTP API state
self.http_api._wifi_signal[channel] = value
self.http_api._ptz_position[channel] = position
self.http_api._ir_state[channel] = enabled
```

**Benefits:**
- Unified state regardless of query method
- Can mix protocols transparently
- Calling either `get_states()` updates the same cache
- Getter methods (`host.wifi_signal()`) work regardless of protocol used

## Battery Device Optimization

### Wake State Behavior

**Asleep State:**
- Only `NONE_WAKING_COMMANDS` are queried
- Examples: GetIrLights, GetMdState, GetBatteryInfo, GetEvents
- Device remains asleep, preserving battery

**Awake State:**
- All commands queried, including `WAKING_COMMANDS`
- Examples: GetWhiteLed, GetAiCfg, GetPtzCurPos
- Device can be woken for important state updates

### Example Wake Logic

```python
# Check if any channel has battery
any_battery = any(self.http_api.supported(ch, "battery") for ch in self.http_api._channels)
all_wake = all(wake.values())

# Only include command if device is awake OR command is non-waking
def inc_cmd(cmd: str, channel: int) -> bool:
    return (channel in cmd_list.get(cmd, []) or not cmd_list) and \
           (wake[channel] or                           # Device is awake
            cmd in NONE_WAKING_COMMANDS or             # Command doesn't wake
            not self.http_api.supported(channel, "battery"))  # Not battery-powered
```

**Wake Strategy:**
```python
wake = {
    0: True,   # Channel 0 is awake - query all commands
    1: False,  # Channel 1 is asleep - only non-waking commands
    2: True,   # Channel 2 is awake - query all commands
}
```

## Error Handling

### Timeout Handling

```python
try:
    async with asyncio.timeout(3 * TIMEOUT):  # 90 seconds
        results = await asyncio.gather(*coroutines, return_exceptions=True)
except asyncio.TimeoutError:
    if self._log_error:
        _LOGGER.warning("Baichuan host %s: Timeout of 3*%s sec getting states",
                       self._host, TIMEOUT)
        self._log_error = False  # Suppress repeated warnings
    return
```

### Individual Command Errors

```python
for result in results:
    if isinstance(result, ReolinkError):
        _LOGGER.debug(result)  # Log but continue
        continue
    if isinstance(result, BaseException):
        raise result  # Re-raise unexpected exceptions
```

**Error Strategy:**
- Individual command failures are logged but don't stop polling
- Unexpected exceptions (bugs) are re-raised
- Timeouts are logged once, then suppressed until success

## Special Considerations

### Privacy Mode

Recent changes handle privacy mode and offline detection:
- Check camera online status via `GetChnTypeInfo` success
- Skip offline cameras in polling loop
- Log warning if camera goes offline

### Hardwired Chime

```python
if self.supported(channel, "hardwired_chime") and \
   channel in cmd_list.get("483", []) and \
   channel not in self._hardwired_chime_settings:
    # Only get state if not cached - cmd_id 483 can make chime rattle
    coroutines.append(self.get_ding_dong_ctrl(channel))
```

Command `483` (GetDingDongCtrl) can cause physical chime to rattle, so it's only queried when:
- Explicitly requested in `cmd_list`
- Not already cached

### Channel Online Check

```python
for channel in self.http_api._channels:
    if not self.http_api.camera_online(channel):
        continue  # Skip all queries for offline cameras
```

Prevents wasted queries and error spam for disconnected NVR channels.

## Usage Examples

### Full State Update (All Channels Awake)

```python
# Query all states, all devices awake
await baichuan.get_states()
```

### Selective Command Update

```python
# Only update WiFi signal and battery info for channels 0 and 1
cmd_list = {
    "115": [0, 1],           # WiFi signal
    "GetBatteryInfo": [0, 1]
}
await baichuan.get_states(cmd_list=cmd_list)
```

### Battery-Aware Update

```python
# Channel 0 is awake, channel 1 is asleep
wake = {0: True, 1: False}
await baichuan.get_states(wake=wake)
# Result: Channel 0 gets all commands, channel 1 only non-waking commands
```

### Host-Only Update

```python
# Only query host-level settings (scenes, chimes)
cmd_list = {
    "GetScene": {None: 1},
    "GetDingDongList": {None: 1}
}
await baichuan.get_states(cmd_list=cmd_list)
```

## Performance Characteristics

### Parallelization Benefits

**Without parallel execution (sequential):**
```
Command 1: 200ms
Command 2: 200ms
Command 3: 200ms
Total: 600ms
```

**With parallel execution (`asyncio.gather`):**
```
All commands: ~200ms
Speedup: 3x
```

For typical polling with 20+ commands, parallelization provides **10-20x speedup**.

### Network Efficiency

**HTTP API:**
- Connection overhead: TCP handshake per request (or connection pooling)
- Data overhead: HTTP headers + JSON formatting
- Typical request size: 500-2000 bytes

**Baichuan:**
- Connection overhead: Single persistent TCP connection
- Data overhead: Binary header + compact XML
- Typical request size: 100-400 bytes

Baichuan is approximately **2-3x more efficient** for continuous polling.

## Related Files

- [baichuan/baichuan.py](../reolink_aio/baichuan/baichuan.py) - Main Baichuan class
- [baichuan/tcp_protocol.py](../reolink_aio/baichuan/tcp_protocol.py) - asyncio TCP protocol handler
- [baichuan/util.py](../reolink_aio/baichuan/util.py) - Encryption and utility functions
- [baichuan/xmls.py](../reolink_aio/baichuan/xmls.py) - XML templates
- [api.py](../reolink_aio/api.py) - HTTP API implementation (compare with Baichuan)
- [const.py](../reolink_aio/const.py) - WAKING_COMMANDS and NONE_WAKING_COMMANDS definitions
