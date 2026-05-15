# Changelog

All notable changes to NX Witness MCP will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
This project uses [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

---

## [2.0.3] - 2026-05-15

### Fixed
- `NXClient` now follows HTTP redirects. NX Cloud relay hosts (`*.relay.vmsproxy.com`) issue `307 Temporary Redirect` responses to region-specific relay nodes (e.g. `relay-us-nyc-2-prod-dp.vmsproxy.com`) on `/rest/v3/login/sessions`. httpx defaults to **not** following redirects, so login failed for any system whose tenant was routed through a redirecting node, surfacing as `HTTPStatusError: Redirect response '307 Temporary Redirect'`. `httpx.AsyncClient` is now constructed with `follow_redirects=True`.

---

## [2.0.2] - 2026-04-08

### Breaking Change
- All 64 tool names have changed. Any saved prompts, scripts, or integrations referencing the old names must be updated.

### Changed
- Renamed all 64 MCP tools to include an explicit operation-category prefix that signals HTTP semantics at a glance: `read_` (39 GET/local-read tools), `write_` (12 POST tools), `update_` (5 PATCH/PUT tools renamed; `nx_update_bookmark` was already correct), `delete_` (3 DELETE tools renamed; the four tools already named `nx_delete_*` were unchanged).
- Added `readOnlyHint` annotations to all tools via `@mcp.tool(annotations={"readOnlyHint": ...})`: `True` for all 39 read tools, `False` for all 25 write/update/delete tools.
- Tools renamed with `read_` prefix (39): `nx_read_list_systems`, `nx_read_server_info`, `nx_read_list_cameras`, `nx_read_get_camera`, `nx_read_get_device_types`, `nx_read_list_device_searches`, `nx_read_get_device_search`, `nx_read_get_device_diagnosis`, `nx_read_get_all_devices_diagnosis`, `nx_read_camera_snapshot`, `nx_read_camera_stream_url`, `nx_read_get_events`, `nx_read_get_log_settings`, `nx_read_get_server_log`, `nx_read_get_audit_log`, `nx_read_get_event_manifest_events`, `nx_read_get_event_manifest_actions`, `nx_read_get_acknowledges`, `nx_read_get_acknowledge`, `nx_read_get_triggers`, `nx_read_get_trigger`, `nx_read_get_rules`, `nx_read_get_rule`, `nx_read_list_analytics_engines`, `nx_read_list_users`, `nx_read_list_servers`, `nx_read_list_storages`, `nx_read_get_storage_status`, `nx_read_list_bookmarks`, `nx_read_get_bookmark`, `nx_read_get_footage`, `nx_read_ptz_get_position`, `nx_read_ptz_get_presets`, `nx_read_virtual_list_uploads`, `nx_read_virtual_get_upload_status`, `nx_read_list_integrations`, `nx_read_get_integration`, `nx_read_get_device_io`, `nx_read_get_device_status`.
- Tools renamed with `write_` prefix (12): `nx_write_create_device`, `nx_write_start_device_search`, `nx_write_acknowledge_event`, `nx_write_create_generic_event`, `nx_write_fire_trigger`, `nx_write_create_rule`, `nx_write_reset_rules`, `nx_write_create_bookmark`, `nx_write_ptz_set_position`, `nx_write_ptz_move`, `nx_write_ptz_activate_preset`, `nx_write_virtual_start_upload`.
- Tools renamed with `update_` prefix (5): `nx_update_replace_device`, `nx_update_modify_device`, `nx_update_replace_rule`, `nx_update_modify_rule`, `nx_update_set_device_io`. (`nx_update_bookmark` unchanged — already correctly named.)
- Tools renamed with `delete_` prefix (3): `nx_delete_stop_device_search`, `nx_delete_ptz_stop`, `nx_delete_virtual_cancel_upload`. (`nx_delete_device`, `nx_delete_rule`, `nx_delete_bookmark`, `nx_delete_analytics_integration` unchanged — already correctly named.)
- Updated 8 cross-references in docstrings and `Field` descriptions to use the new tool names.

---

## [2.0.1] - 2026-04-01

### Fixed
- Moved `system: SYS` parameter to first position in all 18 tool functions where it followed parameters with default values, causing `SyntaxError: non-default argument follows default argument` on import (`nx_list_cameras`, `nx_create_device`, `nx_start_device_search`, `nx_camera_snapshot`, `nx_get_events`, `nx_get_log_settings`, `nx_get_server_log`, `nx_get_audit_log`, `nx_acknowledge_event`, `nx_create_generic_event`, `nx_fire_trigger`, `nx_list_bookmarks`, `nx_create_bookmark`, `nx_update_bookmark`, `nx_get_footage`, `nx_ptz_set_position`, `nx_ptz_move`, `nx_ptz_activate_preset`).

---

## [2.0.0] - 2026-04-01

### Breaking Change
- `system` parameter is now **required** on all tools (was optional, defaulting to the first configured system). This forces the caller to explicitly choose a system on every tool call, which fixes a UX/discoverability issue where Claude Desktop would silently omit the optional parameter and only ever query the default system. Call `nx_list_systems` first to discover available system names.

### Changed
- `nx_list_systems` docstring updated to prominently signal "call this first" so Claude Desktop knows to discover systems before issuing other tool calls
- `_sys_desc()` updated to say "Required" instead of "Defaults to … if omitted"

### Fixed
- `nx_start_device_search`: corrected credential field example from `pw_field` to `password` — the NX Witness API spec uses `pw_field` as a schema sentinel for write-only password fields, but the actual HTTP body key is `password`; using `pw_field` returned a 422 Unprocessable Entity
- `nx_get_camera`: offline devices now return a structured error dict instead of an unhandled 404 exception; the response includes the device ID and guidance to use `nx_list_cameras` or `nx_start_device_search` for offline device info
- `nx_list_cameras`: updated docstring to note that `detailed=true` may silently omit offline devices on some NX Witness server versions; summary mode is the reliable path for enumerating all devices

### Documentation
- Added namespace clarification to README: explains that this server registers as `"nx-witness"` and that having a second NX connector registered simultaneously creates two independent namespaces with independent permission settings

---

## [1.0.0] - 2026-03-31

### Added
- Initial release of NX Witness MCP
- Multi-system support — connect to and switch between multiple NX Witness sites from a single server
- Bearer token authentication with automatic session management
- Support for three connection patterns: direct IP/hostname, vmsproxy relay, and Tailscale
- Full camera management: list, inspect, snapshot, live stream URL
- PTZ control: move, stop, get position, presets, tours
- Recording: footage retrieval, recording statistics
- Storage management: list, status, forecast, add/update/delete
- Layout and video wall management
- Showreel management
- Bookmark creation, retrieval, and management
- Event rules: list, create, modify, replace, reset
- Generic event creation and soft trigger firing
- User and user group management with permissions
- Virtual device support including file uploads
- Integration and analytics engine management
- Metrics: values, alarms, rules manifest
- System tools: server info, site info, license, audit log, server log, settings
- LDAP configuration and sync support
- Cloud bind/unbind and sync status
- Database backup creation and restoration
- Web page resource management
- Lookup list management
