# Changelog

All notable changes to NX Witness MCP will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
This project uses [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

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
