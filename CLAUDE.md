# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`reolink_aio` is a Python package providing an async API for Reolink IP cameras and NVRs. It supports both HTTP-based JSON API and Baichuan TCP protocol for real-time events. The library is officially authorized by Reolink.

**Key Requirements:**
- Python 3.11+
- Dependencies: aiohttp, aiortsp, orjson, pycryptodomex, typing_extensions

## Development Commands

### Installation
```bash
pip install -r requirements.txt
pip install .
```

### Linting and Code Quality
```bash
# Run all quality checks (as CI does)
pylint reolink_aio
flake8 reolink_aio --count --select=E9,F63,F7,F82 --show-source --statistics
flake8 reolink_aio --count --exit-zero --max-line-length=175 --statistics
isort reolink_aio
black --check reolink_aio
mypy reolink_aio

# Auto-fix formatting
isort reolink_aio
black reolink_aio
```

### Testing
```bash
# Note: Tests require actual Reolink hardware at configured IP
# Edit tests/test.py to set HOST, USER, PASSWORD before running
python -m pytest tests/
```

### Code Style
- Max line length: 175 characters (configured in .flake8 and pylintrc)
- Use Black for formatting
- Many pylint checks disabled (see pylintrc) - be aware of the existing style
- F401 (unused imports) ignored in `__init__.py` files

## Architecture

### Two Communication Protocols

The library implements **dual-protocol architecture** for different use cases:

1. **HTTP JSON API** ([api.py](reolink_aio/api.py)) - Main protocol
   - Login/logout with session management
   - Get/set device settings and capabilities
   - Control camera features (IR lights, spotlight, siren, PTZ, etc.)
   - Retrieve snapshots and stream URLs
   - ONVIF subscription for events (legacy method)

2. **Baichuan TCP Protocol** ([baichuan/](reolink_aio/baichuan/)) - Real-time events
   - Encrypted TCP connection for push notifications
   - Battery-powered device support (wake-on-LAN style)
   - Real-time motion/AI detection events
   - More efficient for continuous monitoring
   - Based on work from neolink project

### Core Classes

**`Host` class** ([api.py](reolink_aio/api.py)) - Main API interface
- Represents a single camera or NVR with multiple channels
- Manages HTTP session and Baichuan connection
- Caches device capabilities and state
- Channel-based operations (channel 0, 1, 2, etc.)
- ~7000 lines - most API functionality lives here

**`Baichuan` class** ([baichuan/baichuan.py](reolink_aio/baichuan/baichuan.py)) - TCP protocol handler
- Encrypted communication (AES encryption)
- Callback registration for events
- Keep-alive management
- Battery device wake command handling

### Key Design Patterns

**Channel-based Architecture:**
- NVRs have multiple channels (one per camera)
- Standalone cameras typically use channel 0
- Most methods accept a channel parameter
- Device capabilities cached per-channel in dictionaries

**State Caching:**
- `get_host_data()` - Fetches and caches device capabilities (model, ports, HDD, etc.)
- `get_states()` - Fetches and caches current feature states (motion detection, IR, recording, etc.)
- State stored in instance variables (e.g., `_ir_state`, `_ftp_state`, `_ptz_presets`)
- Methods like `ir_enabled(channel)` read from cache, `set_ir_lights(channel, enabled)` modify state

**Waking vs Non-Waking Commands:**
- Battery devices sleep to save power
- Commands categorized in [const.py](reolink_aio/const.py): `WAKING_COMMANDS` vs `NONE_WAKING_COMMANDS`
- Non-waking commands queried via Baichuan protocol when device is asleep
- Waking commands trigger device wake-up before execution

**Software Version Management:**
- [software_version.py](reolink_aio/software_version.py) - Version comparison and minimum firmware checks
- Features may require specific firmware versions
- `MINIMUM_FIRMWARE` constants define requirements

### Important Files

- [api.py](reolink_aio/api.py) - Main Host class, HTTP API implementation (~7k lines)
- [baichuan/baichuan.py](reolink_aio/baichuan/baichuan.py) - TCP protocol implementation
- [baichuan/tcp_protocol.py](reolink_aio/baichuan/tcp_protocol.py) - asyncio TCP protocol handler
- [exceptions.py](reolink_aio/exceptions.py) - Custom exception hierarchy
- [enums.py](reolink_aio/enums.py) - Type-safe enumerations for API values
- [typings.py](reolink_aio/typings.py) - TypedDict definitions for JSON responses
- [templates.py](reolink_aio/templates.py) - JSON command templates
- [const.py](reolink_aio/const.py) - Constants including command categorization

## Common Patterns

### Adding New Camera Features

When adding support for new camera features:

1. Add command templates to [templates.py](reolink_aio/templates.py) if needed
2. Add state variables to `Host.__init__()` (usually per-channel dicts)
3. Implement getter method to read cached state
4. Implement setter method that:
   - Sends HTTP command via `send_setting()`
   - Updates local cache on success
   - Returns bool indicating success
5. Add capability detection in `get_host_data()` or `get_states()` if needed
6. Categorize command in [const.py](reolink_aio/const.py) (waking vs non-waking) for battery devices
7. Add enum to [enums.py](reolink_aio/enums.py) if feature has typed values

### Error Handling

- Always catch and handle exceptions from [exceptions.py](reolink_aio/exceptions.py)
- `CredentialsInvalidError` - Invalid username/password
- `NotSupportedError` - Device doesn't support feature
- `ReolinkConnectionError` - Network connectivity issues
- `ReolinkTimeoutError` - Request timeout
- `ApiError` - API returned error code (check `rspCode`)

### Privacy Mode Handling

- Privacy mode blocks most API calls
- Recent change: Check camera online status via `GetChnTypeInfo` success (see recent commits)
- Log warning if camera offline but don't fail operations
- Wait 7.5 seconds before retry when getting ConnectionError within 60s of disabling privacy mode

## Version Information

Current version: 0.16.5 (see [setup.py](setup.py))

When bumping version:
- Update version in [setup.py](setup.py)
- Commit with message format: "Bump reolink_aio to X.Y.Z"
