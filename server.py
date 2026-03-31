#!/usr/bin/env python3
"""MCP server for NX Witness VMS — multi-system support."""

import asyncio
import json
import os
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

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

app = Server("nx-witness")


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


def text(data: any) -> list[types.TextContent]:
    return [types.TextContent(type="text", text=json.dumps(data, indent=2))]


def _sys_param() -> dict:
    """Reusable 'system' parameter definition for every tool."""
    names = list(SYSTEMS.keys())
    desc = (
        f"NX system to target. Available: {names}. "
        f"Defaults to '{DEFAULT_SYSTEM}' if omitted."
    )
    return {"system": {"type": "string", "description": desc}}


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [

        # --- System Management ---
        types.Tool(
            name="nx_list_systems",
            description="List all configured NX Witness systems known to this MCP server.",
            inputSchema={"type": "object", "properties": {}},
        ),

        # --- Servers & Devices ---
        types.Tool(
            name="nx_server_info",
            description="Get NX Witness server information including name, version, and system details.",
            inputSchema={
                "type": "object",
                "properties": {**_sys_param()},
            },
        ),
        types.Tool(
            name="nx_list_cameras",
            description="List all cameras/devices. Returns id, name, status, vendor, model, URL, and firmware. Use detailed=true to get full device objects (all fields) — avoids calling nx_get_camera per device.",
            inputSchema={
                "type": "object",
                "properties": {
                    "device_type": {"type": "string", "description": "Optional filter (e.g. 'camera', 'ioModule')"},
                    "detailed": {"type": "boolean", "description": "If true, return full device objects instead of summary fields. Use this when you need firmware, parameters, or other detailed info for multiple devices at once."},
                    **_sys_param(),
                },
            },
        ),
        types.Tool(
            name="nx_get_camera",
            description="Get detailed information about a specific camera/device by its UUID.",
            inputSchema={
                "type": "object",
                "required": ["device_id"],
                "properties": {
                    "device_id": {"type": "string", "description": "Device UUID"},
                    **_sys_param(),
                },
            },
        ),
        types.Tool(
            name="nx_camera_snapshot",
            description="Capture a live snapshot image from a camera. Returns a JPEG image.",
            inputSchema={
                "type": "object",
                "required": ["device_id"],
                "properties": {
                    "device_id": {"type": "string", "description": "Device UUID"},
                    "width": {"type": "integer", "description": "Optional width in pixels"},
                    "height": {"type": "integer", "description": "Optional height in pixels"},
                    **_sys_param(),
                },
            },
        ),
        types.Tool(
            name="nx_camera_stream_url",
            description="Get a signed streaming URL for a camera's live video feed.",
            inputSchema={
                "type": "object",
                "required": ["device_id"],
                "properties": {
                    "device_id": {"type": "string", "description": "Device UUID"},
                    **_sys_param(),
                },
            },
        ),

        # --- Event Log ---
        types.Tool(
            name="nx_get_events",
            description="Query the event log (most recent first). Supports filtering by type, device, text, flags, and time range.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max events to return (default 50)", "default": 50},
                    "event_type": {"type": "string", "description": "Filter by event type e.g. 'cameraMotion', 'cameraDisconnect', 'serverFailure', 'analyticsObject', 'analyticsSdkEvent'"},
                    "event_subtype": {"type": "string", "description": "Analytics subtype for advanced filtering"},
                    "action_type": {"type": "string", "description": "Filter by action type e.g. 'desktopNotification', 'sendEmail', 'pushNotification'"},
                    "device_id": {"type": "string", "description": "Filter by device UUID (eventResourceId)"},
                    "rule_id": {"type": "string", "description": "Filter by rule UUID"},
                    "text": {"type": "string", "description": "Text search in event descriptions"},
                    "flags": {"type": "string", "description": "Filter by flags: 'noFlags', 'acknowledge', or 'videoLinkExists'"},
                    "server_id": {"type": "string", "description": "Limit to a specific server UUID"},
                    "from_ms": {"type": "integer", "description": "Start time as Unix ms"},
                    "duration_ms": {"type": "integer", "description": "Duration in ms from start time"},
                    **_sys_param(),
                },
            },
        ),

        # --- Server Logs ---
        types.Tool(
            name="nx_get_log_settings",
            description="Get server log settings: available log files (main, http, system) and their paths/levels.",
            inputSchema={
                "type": "object",
                "properties": {
                    "server_id": {"type": "string", "description": "Server UUID or 'this' (default) for the current server"},
                    **_sys_param(),
                },
            },
        ),
        types.Tool(
            name="nx_get_server_log",
            description=(
                "Get server application log lines. "
                "Use name='MAIN' for the main log, 'HTTP' for HTTP request log, 'SYSTEM' for the system log. "
                "Returns plain text log lines most-recent-last."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Log name: 'MAIN' (default), 'HTTP', or 'SYSTEM'", "default": "MAIN"},
                    "lines": {"type": "integer", "description": "Number of lines to return (default 200)", "default": 200},
                    **_sys_param(),
                },
            },
        ),

        # --- Audit Log ---
        types.Tool(
            name="nx_get_audit_log",
            description=(
                "Query the system audit log. Records admin/user actions: logins, camera changes, "
                "settings updates, archive views, exports, and more. "
                "Event types include: AR_Login, AR_UnauthorizedLogin, AR_CameraInsert, AR_CameraUpdate, "
                "AR_CameraRemove, AR_UserUpdate, AR_SettingsChange, AR_ExportVideo, AR_ViewArchive, "
                "AR_ViewLive, AR_StorageInsert, AR_StorageUpdate, AR_StorageRemove, AR_ServerUpdate, "
                "AR_ServerRemove, AR_UpdateInstall, AR_SystemmMerge, AR_BEventUpdate, AR_BEventRemove."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max entries to return (default 50)", "default": 50},
                    "event_type": {"type": "string", "description": "Filter by event type e.g. 'AR_Login', 'AR_UnauthorizedLogin', 'AR_SettingsChange'"},
                    "username": {"type": "string", "description": "Filter by username (case-insensitive)"},
                    "from_sec": {"type": "integer", "description": "Start time as Unix epoch seconds"},
                    "to_sec": {"type": "integer", "description": "End time as Unix epoch seconds"},
                    **_sys_param(),
                },
            },
        ),

        # --- Event Manifest ---
        types.Tool(
            name="nx_get_event_manifest_events",
            description="Get the manifest of all available event types supported by this NX Witness server.",
            inputSchema={
                "type": "object",
                "properties": {**_sys_param()},
            },
        ),
        types.Tool(
            name="nx_get_event_manifest_actions",
            description="Get the manifest of all available action types that can be triggered by event rules.",
            inputSchema={
                "type": "object",
                "properties": {**_sys_param()},
            },
        ),

        # --- Acknowledges ---
        types.Tool(
            name="nx_get_acknowledges",
            description="Get all event notifications that require acknowledgement.",
            inputSchema={
                "type": "object",
                "properties": {**_sys_param()},
            },
        ),
        types.Tool(
            name="nx_acknowledge_event",
            description="Acknowledge an event notification. Creates a bookmark for the event.",
            inputSchema={
                "type": "object",
                "required": ["device_id", "action_id", "action_server_id", "start_time_ms"],
                "properties": {
                    "device_id": {"type": "string", "description": "Device UUID from the event"},
                    "action_id": {"type": "string", "description": "Action ID from the event's actionData.id"},
                    "action_server_id": {"type": "string", "description": "Server UUID from the event's actionData"},
                    "start_time_ms": {"type": "integer", "description": "Event timestamp in ms"},
                    "duration_ms": {"type": "integer", "description": "Bookmark duration in ms (default 1000)", "default": 1000},
                    "name": {"type": "string", "description": "Bookmark name (default 'Bookmark')", "default": "Bookmark"},
                    **_sys_param(),
                },
            },
        ),
        types.Tool(
            name="nx_get_acknowledge",
            description="Get a specific acknowledgement notification by ID.",
            inputSchema={
                "type": "object",
                "required": ["ack_id"],
                "properties": {
                    "ack_id": {"type": "string", "description": "Acknowledgement ID"},
                    **_sys_param(),
                },
            },
        ),

        # --- Generic Events ---
        types.Tool(
            name="nx_create_generic_event",
            description="Create a generic (custom) event on the NX Witness server. Useful for triggering rules from external systems.",
            inputSchema={
                "type": "object",
                "required": ["source"],
                "properties": {
                    "source": {"type": "string", "description": "Event source identifier string"},
                    "caption": {"type": "string", "description": "Short event title"},
                    "description": {"type": "string", "description": "Longer event description"},
                    "state": {"type": "string", "description": "'instant', 'active', or 'inactive'", "default": "instant"},
                    "metadata": {"type": "object", "description": "Optional key-value metadata"},
                    **_sys_param(),
                },
            },
        ),

        # --- Soft Triggers ---
        types.Tool(
            name="nx_get_triggers",
            description="List all software (soft) triggers configured on the NX Witness server.",
            inputSchema={
                "type": "object",
                "properties": {**_sys_param()},
            },
        ),
        types.Tool(
            name="nx_get_trigger",
            description="Get details of a specific software trigger by ID.",
            inputSchema={
                "type": "object",
                "required": ["trigger_id"],
                "properties": {
                    "trigger_id": {"type": "string", "description": "Trigger UUID"},
                    **_sys_param(),
                },
            },
        ),
        types.Tool(
            name="nx_fire_trigger",
            description="Fire (activate) a software trigger event.",
            inputSchema={
                "type": "object",
                "required": ["trigger_id"],
                "properties": {
                    "trigger_id": {"type": "string", "description": "Trigger UUID to fire"},
                    "device_id": {"type": "string", "description": "Optional device UUID to associate with the trigger"},
                    "state": {"type": "string", "description": "'started', 'stopped', or 'instant'", "default": "started"},
                    **_sys_param(),
                },
            },
        ),

        # --- Event Rules ---
        types.Tool(
            name="nx_get_rules",
            description="List all event rules configured on the NX Witness server.",
            inputSchema={
                "type": "object",
                "properties": {**_sys_param()},
            },
        ),
        types.Tool(
            name="nx_get_rule",
            description="Get details of a specific event rule by ID.",
            inputSchema={
                "type": "object",
                "required": ["rule_id"],
                "properties": {
                    "rule_id": {"type": "string", "description": "Rule UUID"},
                    **_sys_param(),
                },
            },
        ),
        types.Tool(
            name="nx_create_rule",
            description="Create a new event rule. Provide a full rule object as JSON.",
            inputSchema={
                "type": "object",
                "required": ["rule"],
                "properties": {
                    "rule": {"type": "object", "description": "Full rule definition object"},
                    **_sys_param(),
                },
            },
        ),
        types.Tool(
            name="nx_replace_rule",
            description="Replace an existing event rule entirely (PUT).",
            inputSchema={
                "type": "object",
                "required": ["rule_id", "rule"],
                "properties": {
                    "rule_id": {"type": "string", "description": "Rule UUID"},
                    "rule": {"type": "object", "description": "Full replacement rule object"},
                    **_sys_param(),
                },
            },
        ),
        types.Tool(
            name="nx_modify_rule",
            description="Partially update an existing event rule (PATCH).",
            inputSchema={
                "type": "object",
                "required": ["rule_id", "changes"],
                "properties": {
                    "rule_id": {"type": "string", "description": "Rule UUID"},
                    "changes": {"type": "object", "description": "Fields to update"},
                    **_sys_param(),
                },
            },
        ),
        types.Tool(
            name="nx_delete_rule",
            description="Delete an event rule by ID.",
            inputSchema={
                "type": "object",
                "required": ["rule_id"],
                "properties": {
                    "rule_id": {"type": "string", "description": "Rule UUID to delete"},
                    **_sys_param(),
                },
            },
        ),
        types.Tool(
            name="nx_reset_rules",
            description="Reset ALL event rules to factory defaults. This is destructive and cannot be undone.",
            inputSchema={
                "type": "object",
                "properties": {**_sys_param()},
            },
        ),

        # --- Analytics & Users ---
        types.Tool(
            name="nx_list_analytics_engines",
            description="List all analytics engines (AI/ML plugins) installed on the server.",
            inputSchema={
                "type": "object",
                "properties": {**_sys_param()},
            },
        ),
        types.Tool(
            name="nx_list_users",
            description="List all users configured in the NX Witness system.",
            inputSchema={
                "type": "object",
                "properties": {**_sys_param()},
            },
        ),

        # --- Servers (Extended) ---
        types.Tool(
            name="nx_list_servers",
            description="List all servers in the NX Witness site with their IDs, names, URLs, and status.",
            inputSchema={
                "type": "object",
                "properties": {**_sys_param()},
            },
        ),
        types.Tool(
            name="nx_list_storages",
            description="List all storage locations configured on a specific server.",
            inputSchema={
                "type": "object",
                "required": ["server_id"],
                "properties": {
                    "server_id": {"type": "string", "description": "Server UUID"},
                    **_sys_param(),
                },
            },
        ),
        types.Tool(
            name="nx_get_storage_status",
            description="Get the status of a specific storage location on a server (free space, health, etc.).",
            inputSchema={
                "type": "object",
                "required": ["server_id", "storage_id"],
                "properties": {
                    "server_id": {"type": "string", "description": "Server UUID"},
                    "storage_id": {"type": "string", "description": "Storage UUID"},
                    **_sys_param(),
                },
            },
        ),

        # --- Bookmarks ---
        types.Tool(
            name="nx_list_bookmarks",
            description="List bookmarks for a camera/device. Optionally filter by time range or text search.",
            inputSchema={
                "type": "object",
                "required": ["device_id"],
                "properties": {
                    "device_id": {"type": "string", "description": "Device UUID"},
                    "start_time_ms": {"type": "integer", "description": "Filter bookmarks starting after this time (Unix ms)"},
                    "end_time_ms": {"type": "integer", "description": "Filter bookmarks starting before this time (Unix ms)"},
                    "text": {"type": "string", "description": "Text search filter (name, description, or tag)"},
                    "limit": {"type": "integer", "description": "Maximum number of bookmarks to return"},
                    **_sys_param(),
                },
            },
        ),
        types.Tool(
            name="nx_create_bookmark",
            description="Create a bookmark on a camera/device to mark an important time range in the recorded footage.",
            inputSchema={
                "type": "object",
                "required": ["device_id", "name", "duration_ms"],
                "properties": {
                    "device_id": {"type": "string", "description": "Device UUID"},
                    "name": {"type": "string", "description": "Bookmark name/title"},
                    "duration_ms": {"type": "integer", "description": "Bookmark duration in milliseconds"},
                    "start_time_ms": {"type": "integer", "description": "Bookmark start time (Unix ms). Defaults to current time if omitted."},
                    "description": {"type": "string", "description": "Longer description of the bookmark"},
                    "tags": {"type": "array", "items": {"type": "string"}, "description": "List of tag strings"},
                    **_sys_param(),
                },
            },
        ),
        types.Tool(
            name="nx_get_bookmark",
            description="Get details of a specific bookmark by ID.",
            inputSchema={
                "type": "object",
                "required": ["device_id", "bookmark_id"],
                "properties": {
                    "device_id": {"type": "string", "description": "Device UUID"},
                    "bookmark_id": {"type": "string", "description": "Bookmark UUID"},
                    **_sys_param(),
                },
            },
        ),
        types.Tool(
            name="nx_update_bookmark",
            description="Update fields of an existing bookmark (name, description, time, duration, tags).",
            inputSchema={
                "type": "object",
                "required": ["device_id", "bookmark_id"],
                "properties": {
                    "device_id": {"type": "string", "description": "Device UUID"},
                    "bookmark_id": {"type": "string", "description": "Bookmark UUID"},
                    "name": {"type": "string", "description": "New bookmark name"},
                    "description": {"type": "string", "description": "New description"},
                    "start_time_ms": {"type": "integer", "description": "New start time (Unix ms)"},
                    "duration_ms": {"type": "integer", "description": "New duration in milliseconds"},
                    "tags": {"type": "array", "items": {"type": "string"}, "description": "New list of tags (replaces existing)"},
                    **_sys_param(),
                },
            },
        ),
        types.Tool(
            name="nx_delete_bookmark",
            description="Delete a bookmark by its ID.",
            inputSchema={
                "type": "object",
                "required": ["bookmark_id"],
                "properties": {
                    "bookmark_id": {"type": "string", "description": "Bookmark UUID"},
                    **_sys_param(),
                },
            },
        ),

        # --- Footage ---
        types.Tool(
            name="nx_get_footage",
            description="Get recorded footage chunk info for a device. Returns a list of recorded time periods/chunks. Use to check what footage is available.",
            inputSchema={
                "type": "object",
                "required": ["device_id"],
                "properties": {
                    "device_id": {"type": "string", "description": "Device UUID"},
                    "start_time_ms": {"type": "integer", "description": "Start of time range (Unix ms)"},
                    "end_time_ms": {"type": "integer", "description": "End of time range (Unix ms)"},
                    "detail_level_ms": {"type": "integer", "description": "Chunk granularity in ms (smaller = more detail)"},
                    "max_count": {"type": "integer", "description": "Maximum number of chunks to return"},
                    **_sys_param(),
                },
            },
        ),

        # --- PTZ Control ---
        types.Tool(
            name="nx_ptz_get_position",
            description="Get the current pan/tilt/zoom position of a PTZ camera.",
            inputSchema={
                "type": "object",
                "required": ["device_id"],
                "properties": {
                    "device_id": {"type": "string", "description": "Device UUID of the PTZ camera"},
                    **_sys_param(),
                },
            },
        ),
        types.Tool(
            name="nx_ptz_set_position",
            description="Move a PTZ camera to an absolute pan/tilt/zoom position.",
            inputSchema={
                "type": "object",
                "required": ["device_id", "speed"],
                "properties": {
                    "device_id": {"type": "string", "description": "Device UUID of the PTZ camera"},
                    "speed": {"type": "number", "description": "Movement speed (0.0 to 1.0)"},
                    "pan": {"type": "number", "description": "Pan (X-axis) position"},
                    "tilt": {"type": "number", "description": "Tilt (Y-axis) position"},
                    "zoom": {"type": "number", "description": "Zoom (Z-axis) position"},
                    **_sys_param(),
                },
            },
        ),
        types.Tool(
            name="nx_ptz_move",
            description="Start a continuous PTZ move. Speeds range from -1.0 (full left/down) to 1.0 (full right/up). Call nx_ptz_stop to halt.",
            inputSchema={
                "type": "object",
                "required": ["device_id"],
                "properties": {
                    "device_id": {"type": "string", "description": "Device UUID of the PTZ camera"},
                    "pan": {"type": "number", "description": "Pan speed (-1.0 to 1.0, negative=left, positive=right)"},
                    "tilt": {"type": "number", "description": "Tilt speed (-1.0 to 1.0, negative=down, positive=up)"},
                    "zoom": {"type": "number", "description": "Zoom speed (-1.0 to 1.0, negative=out, positive=in)"},
                    "focus": {"type": "number", "description": "Focus speed (-1.0 to 1.0)"},
                    **_sys_param(),
                },
            },
        ),
        types.Tool(
            name="nx_ptz_stop",
            description="Stop a continuous PTZ move on a camera.",
            inputSchema={
                "type": "object",
                "required": ["device_id"],
                "properties": {
                    "device_id": {"type": "string", "description": "Device UUID of the PTZ camera"},
                    **_sys_param(),
                },
            },
        ),
        types.Tool(
            name="nx_ptz_get_presets",
            description="List all PTZ presets saved on a camera.",
            inputSchema={
                "type": "object",
                "required": ["device_id"],
                "properties": {
                    "device_id": {"type": "string", "description": "Device UUID of the PTZ camera"},
                    **_sys_param(),
                },
            },
        ),
        types.Tool(
            name="nx_ptz_activate_preset",
            description="Move a PTZ camera to a saved preset position.",
            inputSchema={
                "type": "object",
                "required": ["device_id", "preset_id"],
                "properties": {
                    "device_id": {"type": "string", "description": "Device UUID of the PTZ camera"},
                    "preset_id": {"type": "string", "description": "Preset UUID or ID"},
                    "speed": {"type": "number", "description": "Movement speed (0.0 to 1.0, default 0.5)"},
                    **_sys_param(),
                },
            },
        ),

        # --- Virtual Device Uploads (v4, added in 6.1.1) ---
        types.Tool(
            name="nx_virtual_list_uploads",
            description="List active chunk-based uploads for a virtual camera device.",
            inputSchema={
                "type": "object",
                "required": ["device_id"],
                "properties": {
                    "device_id": {"type": "string", "description": "Virtual device UUID"},
                    **_sys_param(),
                },
            },
        ),
        types.Tool(
            name="nx_virtual_start_upload",
            description=(
                "Initiate one or more file uploads to a virtual camera. "
                "Provide a list of file metadata objects, each with: startTimeMs, durationMs, sizeB, md5, container, codec. "
                "Returns uploadId, chunkSizeB, and fileId for each upload session."
            ),
            inputSchema={
                "type": "object",
                "required": ["device_id", "files"],
                "properties": {
                    "device_id": {"type": "string", "description": "Virtual device UUID"},
                    "files": {
                        "type": "array",
                        "description": "List of file metadata objects",
                        "items": {
                            "type": "object",
                            "properties": {
                                "startTimeMs": {"type": "integer", "description": "Recording start time (Unix ms)"},
                                "durationMs": {"type": "integer", "description": "Duration in ms"},
                                "sizeB": {"type": "integer", "description": "File size in bytes"},
                                "md5": {"type": "string", "description": "MD5 hash of file"},
                                "container": {"type": "string", "description": "Container format (e.g. mkv, mp4)"},
                                "codec": {"type": "string", "description": "Video codec (e.g. H264)"},
                            },
                        },
                    },
                    **_sys_param(),
                },
            },
        ),
        types.Tool(
            name="nx_virtual_get_upload_status",
            description="Get status of an in-progress virtual camera upload, including uploadProgressPercent and archiveProgressPercent.",
            inputSchema={
                "type": "object",
                "required": ["device_id", "upload_id"],
                "properties": {
                    "device_id": {"type": "string", "description": "Virtual device UUID"},
                    "upload_id": {"type": "string", "description": "Upload session UUID"},
                    **_sys_param(),
                },
            },
        ),
        types.Tool(
            name="nx_virtual_cancel_upload",
            description="Cancel an in-progress virtual camera upload.",
            inputSchema={
                "type": "object",
                "required": ["device_id", "upload_id"],
                "properties": {
                    "device_id": {"type": "string", "description": "Virtual device UUID"},
                    "upload_id": {"type": "string", "description": "Upload session UUID"},
                    **_sys_param(),
                },
            },
        ),

        # --- Analytics Integrations (DELETE functional in 6.1.1) ---
        types.Tool(
            name="nx_list_integrations",
            description="List all SDK analytics integrations installed on the server. Requires Power User permissions.",
            inputSchema={
                "type": "object",
                "properties": {**_sys_param()},
            },
        ),
        types.Tool(
            name="nx_get_integration",
            description="Get details of a specific SDK analytics integration by ID. Requires Power User permissions.",
            inputSchema={
                "type": "object",
                "required": ["integration_id"],
                "properties": {
                    "integration_id": {"type": "string", "description": "Integration UUID"},
                    **_sys_param(),
                },
            },
        ),
        types.Tool(
            name="nx_delete_analytics_integration",
            description="Remove an SDK analytics integration from the server. This is destructive and cannot be undone.",
            inputSchema={
                "type": "object",
                "required": ["integration_id"],
                "properties": {
                    "integration_id": {"type": "string", "description": "Integration UUID to remove"},
                    **_sys_param(),
                },
            },
        ),

        # --- Device IO & Status ---
        types.Tool(
            name="nx_get_device_io",
            description="Get current IO port states for a device (e.g. door sensors, relays, alarm inputs/outputs).",
            inputSchema={
                "type": "object",
                "required": ["device_id"],
                "properties": {
                    "device_id": {"type": "string", "description": "Device UUID"},
                    **_sys_param(),
                },
            },
        ),
        types.Tool(
            name="nx_set_device_io",
            description="Set IO output port states on a device (e.g. trigger a relay or alarm output).",
            inputSchema={
                "type": "object",
                "required": ["device_id", "ports"],
                "properties": {
                    "device_id": {"type": "string", "description": "Device UUID"},
                    "ports": {
                        "type": "object",
                        "description": "Map of port number to port state. Example: {\"1\": {\"isActive\": true}}",
                        "additionalProperties": {
                            "type": "object",
                            "properties": {
                                "isActive": {"type": "boolean"},
                                "autoResetTimeoutMs": {"type": "integer"},
                            },
                        },
                    },
                    **_sys_param(),
                },
            },
        ),
        types.Tool(
            name="nx_get_device_status",
            description="Get diagnostic/health status for a specific camera or device.",
            inputSchema={
                "type": "object",
                "required": ["device_id"],
                "properties": {
                    "device_id": {"type": "string", "description": "Device UUID"},
                    **_sys_param(),
                },
            },
        ),
    ]


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent | types.ImageContent]:
    sys_name = arguments.get("system")

    # --- System Management ---
    if name == "nx_list_systems":
        return text({
            "systems": list(SYSTEMS.keys()),
            "default": DEFAULT_SYSTEM,
        })

    try:
        c = get_client(sys_name)
    except ValueError as e:
        return text({"error": str(e)})

    # --- Servers & Devices ---
    if name == "nx_server_info":
        return text(await c.get_server_info())

    elif name == "nx_list_cameras":
        devices = await c.list_devices(device_type=arguments.get("device_type"))
        if arguments.get("detailed"):
            return text(devices)
        summary = [{
            "id": d.get("id"), "name": d.get("name"), "status": d.get("status"),
            "vendor": d.get("vendor"), "model": d.get("model"),
            "firmware": d.get("firmware"),
            "url": d.get("url"), "serverId": d.get("serverId"),
            "isManuallyAdded": d.get("isManuallyAdded"),
        } for d in devices]
        return text(summary)

    elif name == "nx_get_camera":
        return text(await c.get_device(arguments["device_id"]))

    elif name == "nx_camera_snapshot":
        b64 = await c.get_camera_snapshot(
            arguments["device_id"],
            width=arguments.get("width"),
            height=arguments.get("height"),
        )
        return [types.ImageContent(type="image", data=b64, mimeType="image/jpeg")]

    elif name == "nx_camera_stream_url":
        return text(await c.get_camera_stream_url(arguments["device_id"]))

    # --- Event Log ---
    elif name == "nx_get_events":
        return text(await c.get_events(
            limit=arguments.get("limit", 50),
            event_type=arguments.get("event_type"),
            event_subtype=arguments.get("event_subtype"),
            action_type=arguments.get("action_type"),
            device_id=arguments.get("device_id"),
            rule_id=arguments.get("rule_id"),
            text=arguments.get("text"),
            flags=arguments.get("flags"),
            server_id=arguments.get("server_id"),
            from_ms=arguments.get("from_ms"),
            duration_ms=arguments.get("duration_ms"),
        ))

    # --- Server Logs ---
    elif name == "nx_get_log_settings":
        return text(await c.get_log_settings(arguments.get("server_id", "this")))

    elif name == "nx_get_server_log":
        log_text = await c.get_server_log(
            name=arguments.get("name", "MAIN"),
            lines=arguments.get("lines", 200),
        )
        return [types.TextContent(type="text", text=log_text)]

    # --- Audit Log ---
    elif name == "nx_get_audit_log":
        return text(await c.get_audit_log(
            limit=arguments.get("limit", 50),
            event_type=arguments.get("event_type"),
            username=arguments.get("username"),
            from_sec=arguments.get("from_sec"),
            to_sec=arguments.get("to_sec"),
        ))

    # --- Event Manifest ---
    elif name == "nx_get_event_manifest_events":
        return text(await c.get_event_manifest_events())

    elif name == "nx_get_event_manifest_actions":
        return text(await c.get_event_manifest_actions())

    # --- Acknowledges ---
    elif name == "nx_get_acknowledges":
        return text(await c.get_acknowledges())

    elif name == "nx_acknowledge_event":
        return text(await c.acknowledge_event(
            device_id=arguments["device_id"],
            action_id=arguments["action_id"],
            action_server_id=arguments["action_server_id"],
            start_time_ms=arguments["start_time_ms"],
            duration_ms=arguments.get("duration_ms", 1000),
            name=arguments.get("name", "Bookmark"),
        ))

    elif name == "nx_get_acknowledge":
        return text(await c.get_acknowledge(arguments["ack_id"]))

    # --- Generic Events ---
    elif name == "nx_create_generic_event":
        return text(await c.create_generic_event(
            source=arguments["source"],
            caption=arguments.get("caption"),
            description=arguments.get("description"),
            metadata=arguments.get("metadata"),
            state=arguments.get("state", "instant"),
        ))

    # --- Soft Triggers ---
    elif name == "nx_get_triggers":
        return text(await c.get_triggers())

    elif name == "nx_get_trigger":
        return text(await c.get_trigger(arguments["trigger_id"]))

    elif name == "nx_fire_trigger":
        return text(await c.fire_trigger(
            trigger_id=arguments["trigger_id"],
            device_id=arguments.get("device_id"),
            state=arguments.get("state", "started"),
        ))

    # --- Event Rules ---
    elif name == "nx_get_rules":
        return text(await c.get_rules())

    elif name == "nx_get_rule":
        return text(await c.get_rule(arguments["rule_id"]))

    elif name == "nx_create_rule":
        return text(await c.create_rule(arguments["rule"]))

    elif name == "nx_replace_rule":
        return text(await c.replace_rule(arguments["rule_id"], arguments["rule"]))

    elif name == "nx_modify_rule":
        return text(await c.modify_rule(arguments["rule_id"], arguments["changes"]))

    elif name == "nx_delete_rule":
        return text(await c.delete_rule(arguments["rule_id"]))

    elif name == "nx_reset_rules":
        return text(await c.reset_rules())

    # --- Analytics & Users ---
    elif name == "nx_list_analytics_engines":
        engines = await c.list_analytics_engines()
        return text([{"id": e.get("id"), "name": e.get("name"), "version": e.get("version"), "pluginId": e.get("pluginId")} for e in engines])

    elif name == "nx_list_users":
        users = await c.list_users()
        return text([{"id": u.get("id"), "name": u.get("name"), "email": u.get("email"), "isEnabled": u.get("isEnabled")} for u in users])

    # --- Servers (Extended) ---
    elif name == "nx_list_servers":
        return text(await c.list_servers())

    elif name == "nx_list_storages":
        return text(await c.list_storages(arguments["server_id"]))

    elif name == "nx_get_storage_status":
        return text(await c.get_storage_status(arguments["server_id"], arguments["storage_id"]))

    # --- Bookmarks ---
    elif name == "nx_list_bookmarks":
        return text(await c.list_bookmarks(
            device_id=arguments["device_id"],
            start_time_ms=arguments.get("start_time_ms"),
            end_time_ms=arguments.get("end_time_ms"),
            text=arguments.get("text"),
            limit=arguments.get("limit"),
        ))

    elif name == "nx_create_bookmark":
        return text(await c.create_bookmark(
            device_id=arguments["device_id"],
            name=arguments["name"],
            duration_ms=arguments["duration_ms"],
            start_time_ms=arguments.get("start_time_ms"),
            description=arguments.get("description"),
            tags=arguments.get("tags"),
        ))

    elif name == "nx_get_bookmark":
        return text(await c.get_bookmark(arguments["device_id"], arguments["bookmark_id"]))

    elif name == "nx_update_bookmark":
        return text(await c.update_bookmark(
            device_id=arguments["device_id"],
            bookmark_id=arguments["bookmark_id"],
            name=arguments.get("name"),
            description=arguments.get("description"),
            start_time_ms=arguments.get("start_time_ms"),
            duration_ms=arguments.get("duration_ms"),
            tags=arguments.get("tags"),
        ))

    elif name == "nx_delete_bookmark":
        return text(await c.delete_bookmark(arguments["bookmark_id"]))

    # --- Footage ---
    elif name == "nx_get_footage":
        return text(await c.get_footage(
            device_id=arguments["device_id"],
            start_time_ms=arguments.get("start_time_ms"),
            end_time_ms=arguments.get("end_time_ms"),
            detail_level_ms=arguments.get("detail_level_ms"),
            max_count=arguments.get("max_count"),
        ))

    # --- PTZ Control ---
    elif name == "nx_ptz_get_position":
        return text(await c.ptz_get_position(arguments["device_id"]))

    elif name == "nx_ptz_set_position":
        return text(await c.ptz_set_position(
            device_id=arguments["device_id"],
            speed=arguments["speed"],
            pan=arguments.get("pan"),
            tilt=arguments.get("tilt"),
            zoom=arguments.get("zoom"),
        ))

    elif name == "nx_ptz_move":
        return text(await c.ptz_move(
            device_id=arguments["device_id"],
            pan=arguments.get("pan"),
            tilt=arguments.get("tilt"),
            zoom=arguments.get("zoom"),
            focus=arguments.get("focus"),
        ))

    elif name == "nx_ptz_stop":
        return text(await c.ptz_stop(arguments["device_id"]))

    elif name == "nx_ptz_get_presets":
        return text(await c.ptz_get_presets(arguments["device_id"]))

    elif name == "nx_ptz_activate_preset":
        return text(await c.ptz_activate_preset(
            device_id=arguments["device_id"],
            preset_id=arguments["preset_id"],
            speed=arguments.get("speed", 0.5),
        ))

    # --- Virtual Device Uploads ---
    elif name == "nx_virtual_list_uploads":
        return text(await c.virtual_list_uploads(arguments["device_id"]))

    elif name == "nx_virtual_start_upload":
        return text(await c.virtual_start_upload(arguments["device_id"], arguments["files"]))

    elif name == "nx_virtual_get_upload_status":
        return text(await c.virtual_get_upload_status(arguments["device_id"], arguments["upload_id"]))

    elif name == "nx_virtual_cancel_upload":
        return text(await c.virtual_cancel_upload(arguments["device_id"], arguments["upload_id"]))

    # --- Analytics Integrations ---
    elif name == "nx_list_integrations":
        return text(await c.list_integrations())

    elif name == "nx_get_integration":
        return text(await c.get_integration(arguments["integration_id"]))

    elif name == "nx_delete_analytics_integration":
        return text(await c.delete_analytics_integration(arguments["integration_id"]))

    # --- Device IO & Status ---
    elif name == "nx_get_device_io":
        return text(await c.get_device_io(arguments["device_id"]))

    elif name == "nx_set_device_io":
        return text(await c.set_device_io(arguments["device_id"], arguments["ports"]))

    elif name == "nx_get_device_status":
        return text(await c.get_device_status(arguments["device_id"]))

    else:
        return text({"error": f"Unknown tool: {name}"})


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
