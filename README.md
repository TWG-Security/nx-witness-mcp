# NX Witness MCP

A Model Context Protocol (MCP) server that connects Claude Code to **NX Witness VMS** (Video Management System), enabling Claude to interact with your security camera systems through natural language.

## What It Does

NX Witness MCP exposes your NX Witness system as a set of Claude tools, allowing you to:

- List and inspect cameras, servers, and storage
- Retrieve live stream URLs and snapshots
- Browse and search recorded footage
- Manage layouts, video walls, and showreels
- Control PTZ cameras (move, presets, tours)
- Manage users, user groups, and permissions
- Create and manage bookmarks, rules, and triggers
- Monitor system health, metrics, and alarms
- Manage integrations and analytics engines
- And much more — the full NX Witness REST API surface

Multi-system support lets you connect to multiple NX Witness sites simultaneously and switch between them.

---

## Prerequisites

- Python 3.9 or newer
- `pip`
- Network access to your NX Witness server(s)
- Claude Code (CLI or desktop app)

---

## Installation

```bash
git clone <repo-url>
cd nx-meta-mcp
pip install -r requirements.txt
```

---

## Configuration

Copy the example config and fill in your system credentials:

```bash
cp nx_systems.example.json nx_systems.json
```

Edit `nx_systems.json` with your actual NX Witness system details. Three connection patterns are supported:

### Direct (LAN or VPN)
```json
{
  "systems": {
    "OfficeMain": {
      "host": "https://192.168.1.100:7001",
      "user": "admin",
      "pass": "your_password"
    }
  }
}
```

### vmsproxy Relay (remote access via NX Cloud relay)
```json
{
  "systems": {
    "RemoteSite": {
      "host": "https://xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx.relay.vmsproxy.com",
      "user": "admin",
      "pass": "your_password"
    }
  }
}
```

### Tailscale (zero-config mesh VPN)
```json
{
  "systems": {
    "RemoteSite": {
      "host": "https://your-host.tail12345.ts.net:7001",
      "user": "admin",
      "pass": "your_password"
    }
  }
}
```

You can define as many systems as needed. `nx_systems.json` is excluded from version control — never commit it.

---

## Running the Server

```bash
python server.py
```

The server communicates over stdio and is intended to be launched by a Claude Code host process, not run directly in a terminal.

---

## Claude Code Integration

Add the server to your Claude Code MCP configuration. In your `claude_desktop_config.json` (or the equivalent settings for your Claude Code install):

```json
{
  "mcpServers": {
    "nx-witness": {
      "command": "python",
      "args": ["/absolute/path/to/nx-meta-mcp/server.py"]
    }
  }
}
```

Or via the Claude Code CLI:

```bash
claude mcp add nx-witness python /absolute/path/to/nx-meta-mcp/server.py
```

Restart Claude Code after adding the server. You should see the NX Witness tools available in Claude.

### A note on namespaces

This server registers itself as `"nx-witness"`. All tools appear in Claude Code under the `mcp__nx-witness__` prefix (e.g. `mcp__nx-witness__nx_list_cameras`).

Some NX Witness installations also expose a built-in MCP connector (sometimes listed as `"NXWitness"` or `"nx-meta"` in Claude Code's connector settings). If both this server and a built-in connector are registered simultaneously, the tools appear in **two independent namespaces** with **independent permission settings** — which can cause confusion about which namespace to use or why enabling one doesn't affect the other.

**Recommendation:** Use only one MCP integration at a time. For full tool coverage and multi-system support, use this server exclusively and remove or disable any other NX Witness connectors.

---

## Available Tools

| Category | Tools |
|----------|-------|
| Systems | `nx_list_systems`, `nx_server_info`, `nx_list_servers` |
| Cameras & Devices | `nx_list_cameras`, `nx_get_camera`, `nx_create_device`, `nx_get_device_status`, `nx_get_device_io`, `nx_set_device_io`, `nx_camera_snapshot`, `nx_camera_stream_url` |
| Recording | `nx_get_footage` |
| PTZ | `nx_ptz_get_position`, `nx_ptz_set_position`, `nx_ptz_move`, `nx_ptz_stop`, `nx_ptz_get_presets`, `nx_ptz_activate_preset` |
| Storage | `nx_list_storages`, `nx_get_storage_status` |
| Users | `nx_list_users` |
| Bookmarks | `nx_list_bookmarks`, `nx_get_bookmark`, `nx_create_bookmark`, `nx_update_bookmark`, `nx_delete_bookmark` |
| Events | `nx_get_events`, `nx_get_event_manifest_events`, `nx_get_event_manifest_actions` |
| Acknowledges | `nx_get_acknowledges`, `nx_acknowledge_event`, `nx_get_acknowledge` |
| Triggers | `nx_get_triggers`, `nx_get_trigger`, `nx_fire_trigger` |
| Rules | `nx_get_rules`, `nx_get_rule`, `nx_create_rule`, `nx_replace_rule`, `nx_modify_rule`, `nx_delete_rule`, `nx_reset_rules` |
| Generic Events | `nx_create_generic_event` |
| Analytics & Integrations | `nx_list_analytics_engines`, `nx_list_integrations`, `nx_get_integration`, `nx_delete_analytics_integration` |
| Virtual Uploads | `nx_virtual_list_uploads`, `nx_virtual_start_upload`, `nx_virtual_get_upload_status`, `nx_virtual_cancel_upload` |
| Logs & Audit | `nx_get_log_settings`, `nx_get_server_log`, `nx_get_audit_log` |

---

## Security Notes

- `nx_systems.json` is excluded from git — keep credentials out of version control
- SSL certificate verification is currently disabled for compatibility with self-signed NX Witness certs
- Use a dedicated NX Witness user with least-privilege permissions for the MCP connection

---

## License

MIT

---

## Changelog

### Unreleased
- Added `nx_create_device` tool — creates a device record via `POST /rest/v4/devices` (physicalId, url, typeId required; name, serverId, mac, credentials, parameters, group, options, schedule, motion optional)
- Fixed README tools table to accurately reflect implemented tools (removed ~20 tools listed but not implemented; added ~25 tools implemented but not listed)

### Previous (undocumented)
- Added device IO tools: `nx_get_device_io`, `nx_set_device_io`, `nx_get_device_status`
- Added full event rules CRUD: `nx_get_rule`, `nx_replace_rule`, `nx_modify_rule`, `nx_delete_rule`, `nx_reset_rules`
- Added event acknowledges: `nx_get_acknowledges`, `nx_acknowledge_event`, `nx_get_acknowledge`
- Added soft trigger tools: `nx_get_triggers`, `nx_get_trigger`, `nx_fire_trigger`
- Added event manifest tools: `nx_get_event_manifest_events`, `nx_get_event_manifest_actions`
- Added bookmark delete: `nx_delete_bookmark`
- Added PTZ set position and stop: `nx_ptz_set_position`, `nx_ptz_stop`
- Added virtual camera upload tools: `nx_virtual_list_uploads`, `nx_virtual_start_upload`, `nx_virtual_get_upload_status`, `nx_virtual_cancel_upload`
- Added analytics integration delete: `nx_delete_analytics_integration`
- Added log settings: `nx_get_log_settings`
- Added multi-system support via `nx_systems.json`
