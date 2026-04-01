#!/usr/bin/env python3
"""MCP server for NX Witness VMS — multi-system support."""

import os
from typing import Annotated, Optional

from fastmcp import FastMCP
from fastmcp.utilities.types import Image
from pydantic import Field

from nx_client import NXClient

# ---------------------------------------------------------------------------
# Multi-system configuration
# ---------------------------------------------------------------------------
# Load from nx_systems.json if present, otherwise fall back to env vars.
# nx_systems.json format:
#   {
#     "systems": {
#       "headquarters": { "host": "https://...", "user": "admin", "pass": "..." },
#       "warehouse":    { "host": "https://...", "user": "admin", "pass": "..." }
#     }
#   }
# ---------------------------------------------------------------------------

import json

_CONFIG_FILE = os.path.join(os.path.dirname(__file__), "nx_systems.json")


def _load_systems() -> dict[str, dict]:
    """Load system configs from nx_systems.json, falling back to env vars."""
    if os.path.exists(_CONFIG_FILE):
        with open(_CONFIG_FILE) as f:
            data = json.load(f)
        systems = data.get("systems", {})
        if systems:
            return systems

    # Fallback: single system from environment variables
    return {
        "default": {
            "host": os.environ.get("NX_HOST", "https://127.0.0.1:7001"),
            "user": os.environ.get("NX_USER", "admin"),
            "pass": os.environ.get("NX_PASS", "admin"),
        }
    }


SYSTEMS: dict[str, dict] = _load_systems()
DEFAULT_SYSTEM: str = next(iter(SYSTEMS))   # first key is the default
_clients: dict[str, NXClient] = {}

mcp = FastMCP("nx-witness")


def get_client(system: str | None = None) -> NXClient:
    """Return (and lazily create) the NXClient for the named system."""
    name = system or DEFAULT_SYSTEM
    if name not in SYSTEMS:
        raise ValueError(
            f"Unknown system '{name}'. Available systems: {list(SYSTEMS.keys())}"
        )
    if name not in _clients:
        cfg = SYSTEMS[name]
        _clients[name] = NXClient(cfg["host"], cfg["user"], cfg["pass"])
    return _clients[name]


def _sys_desc() -> str:
    names = list(SYSTEMS.keys())
    return f"NX system to target. Available: {names}. Defaults to '{DEFAULT_SYSTEM}' if omitted."


# Reusable annotated type for the optional system parameter
SYS = Annotated[Optional[str], Field(default=None, description=_sys_desc())]


# ---------------------------------------------------------------------------
# Tools — System Management
# ---------------------------------------------------------------------------

@mcp.tool()
async def nx_list_systems() -> dict:
    """List all configured NX Witness systems known to this MCP server."""
    return {"systems": list(SYSTEMS.keys()), "default": DEFAULT_SYSTEM}


# ---------------------------------------------------------------------------
# Tools — Servers & Devices
# ---------------------------------------------------------------------------

@mcp.tool()
async def nx_server_info(system: SYS = None) -> dict:
    """Get NX Witness server information including name, version, and system details."""
    return await get_client(system).get_server_info()


@mcp.tool()
async def nx_list_cameras(
    device_type: Annotated[Optional[str], Field(default=None, description="Optional filter (e.g. 'camera', 'ioModule')")] = None,
    detailed: Annotated[bool, Field(default=False, description="If true, return full device objects instead of summary fields. Use this when you need firmware, parameters, or other detailed info for multiple devices at once.")] = False,
    system: SYS = None,
) -> list:
    """List all cameras/devices. Returns id, name, status, vendor, model, URL, and firmware. Use detailed=true to get full device objects (all fields) — avoids calling nx_get_camera per device."""
    devices = await get_client(system).list_devices(device_type=device_type)
    if detailed:
        return devices
    return [{
        "id": d.get("id"), "name": d.get("name"), "status": d.get("status"),
        "vendor": d.get("vendor"), "model": d.get("model"),
        "firmware": d.get("firmware"),
        "url": d.get("url"), "serverId": d.get("serverId"),
        "isManuallyAdded": d.get("isManuallyAdded"),
    } for d in devices]


@mcp.tool()
async def nx_get_camera(
    device_id: Annotated[str, Field(description="Device UUID")],
    system: SYS = None,
) -> dict:
    """Get detailed information about a specific camera/device by its UUID."""
    return await get_client(system).get_device(device_id)


@mcp.tool()
async def nx_camera_snapshot(
    device_id: Annotated[str, Field(description="Device UUID")],
    width: Annotated[Optional[int], Field(default=None, description="Optional width in pixels")] = None,
    height: Annotated[Optional[int], Field(default=None, description="Optional height in pixels")] = None,
    system: SYS = None,
) -> Image:
    """Capture a live snapshot image from a camera. Returns a JPEG image."""
    b64 = await get_client(system).get_camera_snapshot(device_id, width=width, height=height)
    return Image(data=b64, format="jpeg")


@mcp.tool()
async def nx_camera_stream_url(
    device_id: Annotated[str, Field(description="Device UUID")],
    system: SYS = None,
) -> str:
    """Get a signed streaming URL for a camera's live video feed."""
    return await get_client(system).get_camera_stream_url(device_id)


# ---------------------------------------------------------------------------
# Tools — Event Log
# ---------------------------------------------------------------------------

@mcp.tool()
async def nx_get_events(
    limit: Annotated[int, Field(default=50, description="Max events to return (default 50)")] = 50,
    event_type: Annotated[Optional[str], Field(default=None, description="Filter by event type e.g. 'cameraMotion', 'cameraDisconnect', 'serverFailure', 'analyticsObject', 'analyticsSdkEvent'")] = None,
    event_subtype: Annotated[Optional[str], Field(default=None, description="Analytics subtype for advanced filtering")] = None,
    action_type: Annotated[Optional[str], Field(default=None, description="Filter by action type e.g. 'desktopNotification', 'sendEmail', 'pushNotification'")] = None,
    device_id: Annotated[Optional[str], Field(default=None, description="Filter by device UUID (eventResourceId)")] = None,
    rule_id: Annotated[Optional[str], Field(default=None, description="Filter by rule UUID")] = None,
    text: Annotated[Optional[str], Field(default=None, description="Text search in event descriptions")] = None,
    flags: Annotated[Optional[str], Field(default=None, description="Filter by flags: 'noFlags', 'acknowledge', or 'videoLinkExists'")] = None,
    server_id: Annotated[Optional[str], Field(default=None, description="Limit to a specific server UUID")] = None,
    from_ms: Annotated[Optional[int], Field(default=None, description="Start time as Unix ms")] = None,
    duration_ms: Annotated[Optional[int], Field(default=None, description="Duration in ms from start time")] = None,
    system: SYS = None,
) -> list:
    """Query the event log (most recent first). Supports filtering by type, device, text, flags, and time range."""
    return await get_client(system).get_events(
        limit=limit,
        event_type=event_type,
        event_subtype=event_subtype,
        action_type=action_type,
        device_id=device_id,
        rule_id=rule_id,
        text=text,
        flags=flags,
        server_id=server_id,
        from_ms=from_ms,
        duration_ms=duration_ms,
    )


# ---------------------------------------------------------------------------
# Tools — Server Logs
# ---------------------------------------------------------------------------

@mcp.tool()
async def nx_get_log_settings(
    server_id: Annotated[str, Field(default="this", description="Server UUID or 'this' (default) for the current server")] = "this",
    system: SYS = None,
) -> dict:
    """Get server log settings: available log files (main, http, system) and their paths/levels."""
    return await get_client(system).get_log_settings(server_id)


@mcp.tool()
async def nx_get_server_log(
    name: Annotated[str, Field(default="MAIN", description="Log name: 'MAIN' (default), 'HTTP', or 'SYSTEM'")] = "MAIN",
    lines: Annotated[int, Field(default=200, description="Number of lines to return (default 200)")] = 200,
    system: SYS = None,
) -> str:
    """Get server application log lines. Use name='MAIN' for the main log, 'HTTP' for HTTP request log, 'SYSTEM' for the system log. Returns plain text log lines most-recent-last."""
    return await get_client(system).get_server_log(name=name, lines=lines)


# ---------------------------------------------------------------------------
# Tools — Audit Log
# ---------------------------------------------------------------------------

@mcp.tool()
async def nx_get_audit_log(
    limit: Annotated[int, Field(default=50, description="Max entries to return (default 50)")] = 50,
    event_type: Annotated[Optional[str], Field(default=None, description="Filter by event type e.g. 'AR_Login', 'AR_UnauthorizedLogin', 'AR_SettingsChange'")] = None,
    username: Annotated[Optional[str], Field(default=None, description="Filter by username (case-insensitive)")] = None,
    from_sec: Annotated[Optional[int], Field(default=None, description="Start time as Unix epoch seconds")] = None,
    to_sec: Annotated[Optional[int], Field(default=None, description="End time as Unix epoch seconds")] = None,
    system: SYS = None,
) -> list:
    """Query the system audit log. Records admin/user actions: logins, camera changes, settings updates, archive views, exports, and more. Event types include: AR_Login, AR_UnauthorizedLogin, AR_CameraInsert, AR_CameraUpdate, AR_CameraRemove, AR_UserUpdate, AR_SettingsChange, AR_ExportVideo, AR_ViewArchive, AR_ViewLive, AR_StorageInsert, AR_StorageUpdate, AR_StorageRemove, AR_ServerUpdate, AR_ServerRemove, AR_UpdateInstall, AR_SystemmMerge, AR_BEventUpdate, AR_BEventRemove."""
    return await get_client(system).get_audit_log(
        limit=limit,
        event_type=event_type,
        username=username,
        from_sec=from_sec,
        to_sec=to_sec,
    )


# ---------------------------------------------------------------------------
# Tools — Event Manifest
# ---------------------------------------------------------------------------

@mcp.tool()
async def nx_get_event_manifest_events(system: SYS = None) -> list:
    """Get the manifest of all available event types supported by this NX Witness server."""
    return await get_client(system).get_event_manifest_events()


@mcp.tool()
async def nx_get_event_manifest_actions(system: SYS = None) -> list:
    """Get the manifest of all available action types that can be triggered by event rules."""
    return await get_client(system).get_event_manifest_actions()


# ---------------------------------------------------------------------------
# Tools — Acknowledges
# ---------------------------------------------------------------------------

@mcp.tool()
async def nx_get_acknowledges(system: SYS = None) -> list:
    """Get all event notifications that require acknowledgement."""
    return await get_client(system).get_acknowledges()


@mcp.tool()
async def nx_acknowledge_event(
    device_id: Annotated[str, Field(description="Device UUID from the event")],
    action_id: Annotated[str, Field(description="Action ID from the event's actionData.id")],
    action_server_id: Annotated[str, Field(description="Server UUID from the event's actionData")],
    start_time_ms: Annotated[int, Field(description="Event timestamp in ms")],
    duration_ms: Annotated[int, Field(default=1000, description="Bookmark duration in ms (default 1000)")] = 1000,
    name: Annotated[str, Field(default="Bookmark", description="Bookmark name (default 'Bookmark')")] = "Bookmark",
    system: SYS = None,
) -> dict:
    """Acknowledge an event notification. Creates a bookmark for the event."""
    return await get_client(system).acknowledge_event(
        device_id=device_id,
        action_id=action_id,
        action_server_id=action_server_id,
        start_time_ms=start_time_ms,
        duration_ms=duration_ms,
        name=name,
    )


@mcp.tool()
async def nx_get_acknowledge(
    ack_id: Annotated[str, Field(description="Acknowledgement ID")],
    system: SYS = None,
) -> dict:
    """Get a specific acknowledgement notification by ID."""
    return await get_client(system).get_acknowledge(ack_id)


# ---------------------------------------------------------------------------
# Tools — Generic Events
# ---------------------------------------------------------------------------

@mcp.tool()
async def nx_create_generic_event(
    source: Annotated[str, Field(description="Event source identifier string")],
    caption: Annotated[Optional[str], Field(default=None, description="Short event title")] = None,
    description: Annotated[Optional[str], Field(default=None, description="Longer event description")] = None,
    state: Annotated[str, Field(default="instant", description="'instant', 'active', or 'inactive'")] = "instant",
    metadata: Annotated[Optional[dict], Field(default=None, description="Optional key-value metadata")] = None,
    system: SYS = None,
) -> dict:
    """Create a generic (custom) event on the NX Witness server. Useful for triggering rules from external systems."""
    return await get_client(system).create_generic_event(
        source=source,
        caption=caption,
        description=description,
        metadata=metadata,
        state=state,
    )


# ---------------------------------------------------------------------------
# Tools — Soft Triggers
# ---------------------------------------------------------------------------

@mcp.tool()
async def nx_get_triggers(system: SYS = None) -> list:
    """List all software (soft) triggers configured on the NX Witness server."""
    return await get_client(system).get_triggers()


@mcp.tool()
async def nx_get_trigger(
    trigger_id: Annotated[str, Field(description="Trigger UUID")],
    system: SYS = None,
) -> dict:
    """Get details of a specific software trigger by ID."""
    return await get_client(system).get_trigger(trigger_id)


@mcp.tool()
async def nx_fire_trigger(
    trigger_id: Annotated[str, Field(description="Trigger UUID to fire")],
    device_id: Annotated[Optional[str], Field(default=None, description="Optional device UUID to associate with the trigger")] = None,
    state: Annotated[str, Field(default="started", description="'started', 'stopped', or 'instant'")] = "started",
    system: SYS = None,
) -> dict:
    """Fire (activate) a software trigger event."""
    return await get_client(system).fire_trigger(
        trigger_id=trigger_id,
        device_id=device_id,
        state=state,
    )


# ---------------------------------------------------------------------------
# Tools — Event Rules
# ---------------------------------------------------------------------------

@mcp.tool()
async def nx_get_rules(system: SYS = None) -> list:
    """List all event rules configured on the NX Witness server."""
    return await get_client(system).get_rules()


@mcp.tool()
async def nx_get_rule(
    rule_id: Annotated[str, Field(description="Rule UUID")],
    system: SYS = None,
) -> dict:
    """Get details of a specific event rule by ID."""
    return await get_client(system).get_rule(rule_id)


@mcp.tool()
async def nx_create_rule(
    rule: Annotated[dict, Field(description="Full rule definition object")],
    system: SYS = None,
) -> dict:
    """Create a new event rule. Provide a full rule object as JSON."""
    return await get_client(system).create_rule(rule)


@mcp.tool()
async def nx_replace_rule(
    rule_id: Annotated[str, Field(description="Rule UUID")],
    rule: Annotated[dict, Field(description="Full replacement rule object")],
    system: SYS = None,
) -> dict:
    """Replace an existing event rule entirely (PUT)."""
    return await get_client(system).replace_rule(rule_id, rule)


@mcp.tool()
async def nx_modify_rule(
    rule_id: Annotated[str, Field(description="Rule UUID")],
    changes: Annotated[dict, Field(description="Fields to update")],
    system: SYS = None,
) -> dict:
    """Partially update an existing event rule (PATCH)."""
    return await get_client(system).modify_rule(rule_id, changes)


@mcp.tool()
async def nx_delete_rule(
    rule_id: Annotated[str, Field(description="Rule UUID to delete")],
    system: SYS = None,
) -> dict:
    """Delete an event rule by ID."""
    return await get_client(system).delete_rule(rule_id)


@mcp.tool()
async def nx_reset_rules(system: SYS = None) -> dict:
    """Reset ALL event rules to factory defaults. This is destructive and cannot be undone."""
    return await get_client(system).reset_rules()


# ---------------------------------------------------------------------------
# Tools — Analytics & Users
# ---------------------------------------------------------------------------

@mcp.tool()
async def nx_list_analytics_engines(system: SYS = None) -> list:
    """List all analytics engines (AI/ML plugins) installed on the server."""
    engines = await get_client(system).list_analytics_engines()
    return [{"id": e.get("id"), "name": e.get("name"), "version": e.get("version"), "pluginId": e.get("pluginId")} for e in engines]


@mcp.tool()
async def nx_list_users(system: SYS = None) -> list:
    """List all users configured in the NX Witness system."""
    users = await get_client(system).list_users()
    return [{"id": u.get("id"), "name": u.get("name"), "email": u.get("email"), "isEnabled": u.get("isEnabled")} for u in users]


# ---------------------------------------------------------------------------
# Tools — Servers (Extended)
# ---------------------------------------------------------------------------

@mcp.tool()
async def nx_list_servers(system: SYS = None) -> list:
    """List all servers in the NX Witness site with their IDs, names, URLs, and status."""
    return await get_client(system).list_servers()


@mcp.tool()
async def nx_list_storages(
    server_id: Annotated[str, Field(description="Server UUID")],
    system: SYS = None,
) -> list:
    """List all storage locations configured on a specific server."""
    return await get_client(system).list_storages(server_id)


@mcp.tool()
async def nx_get_storage_status(
    server_id: Annotated[str, Field(description="Server UUID")],
    storage_id: Annotated[str, Field(description="Storage UUID")],
    system: SYS = None,
) -> dict:
    """Get the status of a specific storage location on a server (free space, health, etc.)."""
    return await get_client(system).get_storage_status(server_id, storage_id)


# ---------------------------------------------------------------------------
# Tools — Bookmarks
# ---------------------------------------------------------------------------

@mcp.tool()
async def nx_list_bookmarks(
    device_id: Annotated[str, Field(description="Device UUID")],
    start_time_ms: Annotated[Optional[int], Field(default=None, description="Filter bookmarks starting after this time (Unix ms)")] = None,
    end_time_ms: Annotated[Optional[int], Field(default=None, description="Filter bookmarks starting before this time (Unix ms)")] = None,
    text: Annotated[Optional[str], Field(default=None, description="Text search filter (name, description, or tag)")] = None,
    limit: Annotated[Optional[int], Field(default=None, description="Maximum number of bookmarks to return")] = None,
    system: SYS = None,
) -> list:
    """List bookmarks for a camera/device. Optionally filter by time range or text search."""
    return await get_client(system).list_bookmarks(
        device_id=device_id,
        start_time_ms=start_time_ms,
        end_time_ms=end_time_ms,
        text=text,
        limit=limit,
    )


@mcp.tool()
async def nx_create_bookmark(
    device_id: Annotated[str, Field(description="Device UUID")],
    name: Annotated[str, Field(description="Bookmark name/title")],
    duration_ms: Annotated[int, Field(description="Bookmark duration in milliseconds")],
    start_time_ms: Annotated[Optional[int], Field(default=None, description="Bookmark start time (Unix ms). Defaults to current time if omitted.")] = None,
    description: Annotated[Optional[str], Field(default=None, description="Longer description of the bookmark")] = None,
    tags: Annotated[Optional[list[str]], Field(default=None, description="List of tag strings")] = None,
    system: SYS = None,
) -> dict:
    """Create a bookmark on a camera/device to mark an important time range in the recorded footage."""
    return await get_client(system).create_bookmark(
        device_id=device_id,
        name=name,
        duration_ms=duration_ms,
        start_time_ms=start_time_ms,
        description=description,
        tags=tags,
    )


@mcp.tool()
async def nx_get_bookmark(
    device_id: Annotated[str, Field(description="Device UUID")],
    bookmark_id: Annotated[str, Field(description="Bookmark UUID")],
    system: SYS = None,
) -> dict:
    """Get details of a specific bookmark by ID."""
    return await get_client(system).get_bookmark(device_id, bookmark_id)


@mcp.tool()
async def nx_update_bookmark(
    device_id: Annotated[str, Field(description="Device UUID")],
    bookmark_id: Annotated[str, Field(description="Bookmark UUID")],
    name: Annotated[Optional[str], Field(default=None, description="New bookmark name")] = None,
    description: Annotated[Optional[str], Field(default=None, description="New description")] = None,
    start_time_ms: Annotated[Optional[int], Field(default=None, description="New start time (Unix ms)")] = None,
    duration_ms: Annotated[Optional[int], Field(default=None, description="New duration in milliseconds")] = None,
    tags: Annotated[Optional[list[str]], Field(default=None, description="New list of tags (replaces existing)")] = None,
    system: SYS = None,
) -> dict:
    """Update fields of an existing bookmark (name, description, time, duration, tags)."""
    return await get_client(system).update_bookmark(
        device_id=device_id,
        bookmark_id=bookmark_id,
        name=name,
        description=description,
        start_time_ms=start_time_ms,
        duration_ms=duration_ms,
        tags=tags,
    )


@mcp.tool()
async def nx_delete_bookmark(
    bookmark_id: Annotated[str, Field(description="Bookmark UUID")],
    system: SYS = None,
) -> dict:
    """Delete a bookmark by its ID."""
    return await get_client(system).delete_bookmark(bookmark_id)


# ---------------------------------------------------------------------------
# Tools — Footage
# ---------------------------------------------------------------------------

@mcp.tool()
async def nx_get_footage(
    device_id: Annotated[str, Field(description="Device UUID")],
    start_time_ms: Annotated[Optional[int], Field(default=None, description="Start of time range (Unix ms)")] = None,
    end_time_ms: Annotated[Optional[int], Field(default=None, description="End of time range (Unix ms)")] = None,
    detail_level_ms: Annotated[Optional[int], Field(default=None, description="Chunk granularity in ms (smaller = more detail)")] = None,
    max_count: Annotated[Optional[int], Field(default=None, description="Maximum number of chunks to return")] = None,
    system: SYS = None,
) -> list:
    """Get recorded footage chunk info for a device. Returns a list of recorded time periods/chunks. Use to check what footage is available."""
    return await get_client(system).get_footage(
        device_id=device_id,
        start_time_ms=start_time_ms,
        end_time_ms=end_time_ms,
        detail_level_ms=detail_level_ms,
        max_count=max_count,
    )


# ---------------------------------------------------------------------------
# Tools — PTZ Control
# ---------------------------------------------------------------------------

@mcp.tool()
async def nx_ptz_get_position(
    device_id: Annotated[str, Field(description="Device UUID of the PTZ camera")],
    system: SYS = None,
) -> dict:
    """Get the current pan/tilt/zoom position of a PTZ camera."""
    return await get_client(system).ptz_get_position(device_id)


@mcp.tool()
async def nx_ptz_set_position(
    device_id: Annotated[str, Field(description="Device UUID of the PTZ camera")],
    speed: Annotated[float, Field(description="Movement speed (0.0 to 1.0)")],
    pan: Annotated[Optional[float], Field(default=None, description="Pan (X-axis) position")] = None,
    tilt: Annotated[Optional[float], Field(default=None, description="Tilt (Y-axis) position")] = None,
    zoom: Annotated[Optional[float], Field(default=None, description="Zoom (Z-axis) position")] = None,
    system: SYS = None,
) -> dict:
    """Move a PTZ camera to an absolute pan/tilt/zoom position."""
    return await get_client(system).ptz_set_position(
        device_id=device_id,
        speed=speed,
        pan=pan,
        tilt=tilt,
        zoom=zoom,
    )


@mcp.tool()
async def nx_ptz_move(
    device_id: Annotated[str, Field(description="Device UUID of the PTZ camera")],
    pan: Annotated[Optional[float], Field(default=None, description="Pan speed (-1.0 to 1.0, negative=left, positive=right)")] = None,
    tilt: Annotated[Optional[float], Field(default=None, description="Tilt speed (-1.0 to 1.0, negative=down, positive=up)")] = None,
    zoom: Annotated[Optional[float], Field(default=None, description="Zoom speed (-1.0 to 1.0, negative=out, positive=in)")] = None,
    focus: Annotated[Optional[float], Field(default=None, description="Focus speed (-1.0 to 1.0)")] = None,
    system: SYS = None,
) -> dict:
    """Start a continuous PTZ move. Speeds range from -1.0 (full left/down) to 1.0 (full right/up). Call nx_ptz_stop to halt."""
    return await get_client(system).ptz_move(
        device_id=device_id,
        pan=pan,
        tilt=tilt,
        zoom=zoom,
        focus=focus,
    )


@mcp.tool()
async def nx_ptz_stop(
    device_id: Annotated[str, Field(description="Device UUID of the PTZ camera")],
    system: SYS = None,
) -> dict:
    """Stop a continuous PTZ move on a camera."""
    return await get_client(system).ptz_stop(device_id)


@mcp.tool()
async def nx_ptz_get_presets(
    device_id: Annotated[str, Field(description="Device UUID of the PTZ camera")],
    system: SYS = None,
) -> list:
    """List all PTZ presets saved on a camera."""
    return await get_client(system).ptz_get_presets(device_id)


@mcp.tool()
async def nx_ptz_activate_preset(
    device_id: Annotated[str, Field(description="Device UUID of the PTZ camera")],
    preset_id: Annotated[str, Field(description="Preset UUID or ID")],
    speed: Annotated[float, Field(default=0.5, description="Movement speed (0.0 to 1.0, default 0.5)")] = 0.5,
    system: SYS = None,
) -> dict:
    """Move a PTZ camera to a saved preset position."""
    return await get_client(system).ptz_activate_preset(
        device_id=device_id,
        preset_id=preset_id,
        speed=speed,
    )


# ---------------------------------------------------------------------------
# Tools — Virtual Device Uploads (v4, added in 6.1.1)
# ---------------------------------------------------------------------------

@mcp.tool()
async def nx_virtual_list_uploads(
    device_id: Annotated[str, Field(description="Virtual device UUID")],
    system: SYS = None,
) -> list:
    """List active chunk-based uploads for a virtual camera device."""
    return await get_client(system).virtual_list_uploads(device_id)


@mcp.tool()
async def nx_virtual_start_upload(
    device_id: Annotated[str, Field(description="Virtual device UUID")],
    files: Annotated[list[dict], Field(description="List of file metadata objects. Each item: startTimeMs, durationMs, sizeB, md5, container, codec.")],
    system: SYS = None,
) -> dict:
    """Initiate one or more file uploads to a virtual camera. Provide a list of file metadata objects, each with: startTimeMs, durationMs, sizeB, md5, container, codec. Returns uploadId, chunkSizeB, and fileId for each upload session."""
    return await get_client(system).virtual_start_upload(device_id, files)


@mcp.tool()
async def nx_virtual_get_upload_status(
    device_id: Annotated[str, Field(description="Virtual device UUID")],
    upload_id: Annotated[str, Field(description="Upload session UUID")],
    system: SYS = None,
) -> dict:
    """Get status of an in-progress virtual camera upload, including uploadProgressPercent and archiveProgressPercent."""
    return await get_client(system).virtual_get_upload_status(device_id, upload_id)


@mcp.tool()
async def nx_virtual_cancel_upload(
    device_id: Annotated[str, Field(description="Virtual device UUID")],
    upload_id: Annotated[str, Field(description="Upload session UUID")],
    system: SYS = None,
) -> dict:
    """Cancel an in-progress virtual camera upload."""
    return await get_client(system).virtual_cancel_upload(device_id, upload_id)


# ---------------------------------------------------------------------------
# Tools — Analytics Integrations
# ---------------------------------------------------------------------------

@mcp.tool()
async def nx_list_integrations(system: SYS = None) -> list:
    """List all SDK analytics integrations installed on the server. Requires Power User permissions."""
    return await get_client(system).list_integrations()


@mcp.tool()
async def nx_get_integration(
    integration_id: Annotated[str, Field(description="Integration UUID")],
    system: SYS = None,
) -> dict:
    """Get details of a specific SDK analytics integration by ID. Requires Power User permissions."""
    return await get_client(system).get_integration(integration_id)


@mcp.tool()
async def nx_delete_analytics_integration(
    integration_id: Annotated[str, Field(description="Integration UUID to remove")],
    system: SYS = None,
) -> dict:
    """Remove an SDK analytics integration from the server. This is destructive and cannot be undone."""
    return await get_client(system).delete_analytics_integration(integration_id)


# ---------------------------------------------------------------------------
# Tools — Device IO & Status
# ---------------------------------------------------------------------------

@mcp.tool()
async def nx_get_device_io(
    device_id: Annotated[str, Field(description="Device UUID")],
    system: SYS = None,
) -> dict:
    """Get current IO port states for a device (e.g. door sensors, relays, alarm inputs/outputs)."""
    return await get_client(system).get_device_io(device_id)


@mcp.tool()
async def nx_set_device_io(
    device_id: Annotated[str, Field(description="Device UUID")],
    ports: Annotated[dict, Field(description='Map of port number to port state. Example: {"1": {"isActive": true}}')],
    system: SYS = None,
) -> dict:
    """Set IO output port states on a device (e.g. trigger a relay or alarm output)."""
    return await get_client(system).set_device_io(device_id, ports)


@mcp.tool()
async def nx_get_device_status(
    device_id: Annotated[str, Field(description="Device UUID")],
    system: SYS = None,
) -> dict:
    """Get diagnostic/health status for a specific camera or device."""
    return await get_client(system).get_device_status(device_id)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    from middleware import MCPTransportMiddleware

    host = os.environ.get("MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("MCP_PORT", "8000"))

    inner = mcp.streamable_http_app()
    app = MCPTransportMiddleware(inner)
    uvicorn.run(app, host=host, port=port)
