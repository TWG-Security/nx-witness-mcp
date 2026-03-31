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

---

## Available Tools

| Category | Tools |
|----------|-------|
| Systems | `nx_list_systems`, `nx_server_info`, `nx_get_site_info`, `nx_list_servers` |
| Cameras | `nx_list_cameras`, `nx_get_camera`, `nx_camera_snapshot`, `nx_camera_stream_url` |
| Recording | `nx_get_footage`, `nx_get_recording_statistics` |
| PTZ | `nx_ptz_move`, `nx_ptz_get_position`, `nx_ptz_get_presets`, `nx_ptz_activate_preset`, `nx_ptz_list_tours` |
| Storage | `nx_list_storages`, `nx_get_storage_status`, `nx_get_storage_forecast`, `nx_add_storage` |
| Users | `nx_list_users`, `nx_get_user`, `nx_create_user`, `nx_update_user`, `nx_delete_user` |
| User Groups | `nx_list_user_groups`, `nx_get_user_group`, `nx_create_user_group`, `nx_update_user_group` |
| Layouts | `nx_list_layouts`, `nx_get_layout`, `nx_create_layout`, `nx_update_layout` |
| Video Walls | `nx_list_video_walls`, `nx_get_video_wall`, `nx_create_video_wall` |
| Bookmarks | `nx_list_bookmarks`, `nx_get_bookmark`, `nx_create_bookmark`, `nx_update_bookmark` |
| Events & Rules | `nx_get_events`, `nx_get_rules`, `nx_create_rule`, `nx_create_generic_event`, `nx_fire_trigger` |
| Integrations | `nx_list_integrations`, `nx_get_integration`, `nx_list_analytics_engines` |
| Metrics | `nx_get_metrics_values`, `nx_get_metrics_alarms`, `nx_get_metrics_rules` |
| System | `nx_get_license`, `nx_get_server_log`, `nx_get_audit_log`, `nx_get_server_settings` |
| Virtual Devices | `nx_list_all_virtual_devices`, `nx_create_virtual_device`, `nx_update_virtual_device` |

---

## Security Notes

- `nx_systems.json` is excluded from git — keep credentials out of version control
- SSL certificate verification is currently disabled for compatibility with self-signed NX Witness certs
- Use a dedicated NX Witness user with least-privilege permissions for the MCP connection

---

## License

MIT
