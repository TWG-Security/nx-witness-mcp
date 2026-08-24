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
- Check which Nx software build a site is running and push build upgrades to it
- And much more — the full NX Witness REST API surface

Multi-system support lets you connect to multiple NX Witness sites simultaneously. Every tool requires a `system` parameter — call `nx_read_list_systems` first to discover available system names, then pass one to each subsequent tool call.

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

The server runs over **Streamable HTTP** (served by uvicorn). It binds to `MCP_HOST` (default `0.0.0.0`) and the port from **`PORT`** (falling back to `MCP_PORT`, then `8000`) and exposes the MCP endpoint at `/mcp`. A plain `GET /healthz` returns `200 ok` for liveness probes. Override host/port with environment variables:

```bash
MCP_HOST=127.0.0.1 PORT=9000 python server.py
```

`PORT` takes precedence so the server drops straight into platforms (like the TWG MCP Control Plane) that inject a `PORT` at runtime; `MCP_PORT` is still honored for existing deployments.

---

## Running with Docker

The repo ships a `Dockerfile`, `.dockerignore`, and `docker-compose.yml` for containerized deployment.

### Build the image

```bash
docker build -t nx-witness-mcp .
```

### Run a container

Credentials are supplied at runtime as environment variables — they are never baked into the image:

```bash
docker run -d --name nx-witness-mcp -p 8000:8000 \
  -e NX_HOST="https://192.168.1.100:7001" \
  -e NX_USER="admin" \
  -e NX_PASS="your_password" \
  nx-witness-mcp
```

The server is then reachable at `http://localhost:8000/mcp`.

### Docker Compose (and Dockhand)

```bash
docker compose up -d
```

`docker-compose.yml` reads its `NX_*` values from the environment (or an optional, gitignored `.env` file). This stack can also be adopted and managed by **Dockhand**.

### Supplying secrets with Infisical

The image is intentionally **credential-agnostic** — it only reads `NX_HOST` / `NX_USER` / `NX_PASS` from the environment. Two ways to wire in Infisical:

1. **Inject at deploy time (recommended):** keep the image generic and let Infisical place the `NX_*` variables into the container's environment — via the Infisical Kubernetes operator, an agent/sidecar, Dockhand's env settings, or by wrapping the launch:

   ```bash
   infisical run --env=prod -- docker compose up -d
   ```

2. **Bake the Infisical CLI into the image:** for a self-fetching container, the image can be extended to install the `infisical` CLI and change the start command to `infisical run -- python server.py`, passing a machine-identity `INFISICAL_TOKEN` plus project/environment IDs as env vars. (Not configured by default.)

### Multi-system config in Docker

For multiple NX Witness sites you have three options — the two env-var forms from
[Multiple systems](#multiple-systems) (per-site `NX_SYSTEM_*` vars or a single `NX_SYSTEMS`
JSON value), or a bind-mounted file.

**A. Env vars (no file mount).** Pass per-site `NX_SYSTEM_*` vars, or one `NX_SYSTEMS` JSON
value:

```bash
docker run -d -p 8000:8000 \
  -e NX_SYSTEM_OfficeMain_HOST=https://192.168.1.100:7001 -e NX_SYSTEM_OfficeMain_USER=admin -e NX_SYSTEM_OfficeMain_PASS=... \
  -e NX_SYSTEM_Warehouse_HOST=https://10.0.5.20:7001 -e NX_SYSTEM_Warehouse_USER=admin -e NX_SYSTEM_Warehouse_PASS=... \
  nx-witness-mcp
```

**B. Bind-mount a file.** Mount an `nx_systems.json` (takes precedence over both `NX_SYSTEMS`
and the `NX_*` vars):

```bash
docker run -d -p 8000:8000 \
  -v "$(pwd)/nx_systems.json:/app/nx_systems.json:ro" \
  nx-witness-mcp
```

(Or uncomment the `volumes:` block in `docker-compose.yml`.)

---

## Deploying on the TWG MCP Control Plane (migration note)

This server is ready for the control plane's **Docker build (build-from-git)** path. The
platform clones this repo, runs `docker build`, starts the image as an isolated container
(`--restart unless-stopped`), injects `PORT` plus the env vars below at runtime, and puts a
**gateway** in front of it — LLM clients never reach the container directly.

| Item | Value |
|------|-------|
| **Transport** | Streamable HTTP (JSON-RPC 2.0 over HTTP) |
| **Endpoint path** | `/mcp` — set this as the server's **Endpoint path** in the control plane |
| **Listen address** | `0.0.0.0` on the injected `PORT` (fallback `MCP_PORT`, then `8000`) |
| **Health check** | `GET /healthz` → `200 ok` (platform also falls back to an MCP `initialize` probe) |
| **Deploy path** | **Docker build** (it already speaks HTTP — the Command/stdio path is *not* needed) |

### Environment variables

| Variable | Secret? | Purpose | Default |
|----------|:-------:|---------|---------|
| `NX_SYSTEM_<NAME>_HOST` / `_USER` / `_PASS` | `_PASS` **yes** | **Multiple** NX sites, one set of vars per site (see [Multiple systems](#multiple-systems)). `<NAME>` becomes the system name. | — |
| `NX_SYSTEMS` | **yes** | **Multiple** NX sites as one JSON value (alternative to the flat vars above; see [Multiple systems](#multiple-systems)). | — |
| `NX_HOST` | no | Single-system NX Witness base URL, e.g. `https://192.168.1.100:7001` | `https://127.0.0.1:7001` |
| `NX_USER` | no | Single-system NX Witness username | `admin` |
| `NX_PASS` | **yes** | Single-system NX Witness password | `admin` |
| `MCP_HOST` | no | Bind address | `0.0.0.0` |
| `PORT` | no | Listen port (injected by the platform) | `8000` |
| `MCP_PORT` | no | Legacy listen-port fallback (used only if `PORT` is unset) | — |

No secrets are baked into the image, the Dockerfile, or git history — credentials are read
from the environment at runtime, and `nx_systems.json` (multi-system credentials) is git- and
docker-ignored. Use `NX_HOST`/`NX_USER`/`NX_PASS` for a single site, or one of the two
multi-system forms below for several.

### Multiple systems

Two env-var forms configure multiple NX sites (no file mount needed). Use whichever your
platform makes easier — they produce identical results.

**A. Per-site variables (flat).** Three variables per site, named
`NX_SYSTEM_<NAME>_HOST` / `_USER` / `_PASS`. Mark the `_PASS` vars secret.

```
NX_SYSTEM_OfficeMain_HOST = https://192.168.1.100:7001
NX_SYSTEM_OfficeMain_USER = admin
NX_SYSTEM_OfficeMain_PASS = ...            (secret)
NX_SYSTEM_Warehouse_HOST  = https://10.0.5.20:7001
NX_SYSTEM_Warehouse_USER  = admin
NX_SYSTEM_Warehouse_PASS  = ...            (secret)
```

- `<NAME>` (`OfficeMain`, `Warehouse`) is the system name — exactly what you pass as the
  `system` argument to every tool, and what `nx_read_list_systems` returns. Names are
  case-sensitive and may contain underscores (e.g. `NX_SYSTEM_Bethel_Church_HOST` →
  `Bethel_Church`).
- A site is included once it has a `_HOST`. Add a site by adding another `NX_SYSTEM_*` set.

**B. One JSON variable.** Set **`NX_SYSTEMS`** (secret) to a JSON object of every site — the
same schema as `nx_systems.json`:

```json
{"systems":{"OfficeMain":{"host":"https://192.168.1.100:7001","user":"admin","pass":"..."},"Warehouse":{"host":"https://10.0.5.20:7001","user":"admin","pass":"..."}}}
```

Each JSON key is a system name; add or remove a site by editing this one value.

**Resolution order:** `nx_systems.json` file → `NX_SYSTEMS` JSON → `NX_SYSTEM_*` flat vars →
single-system `NX_HOST`/`NX_USER`/`NX_PASS`. The first system found is the default (used only
when a tool is somehow called without the required `system` argument).

### Operator steps

Register the server from this repo's git URL, set the **Endpoint path** to `/mcp`, then add
the environment variables above — `NX_HOST`/`NX_USER`/`NX_PASS` for a single site, or the
`NX_SYSTEM_*` flat vars (or `NX_SYSTEMS`) for several; mark every password variable secret.
Add any credential your deployment platform requires to clone a private repository. Once the
server is running, attach it to a gateway.

### Governance annotations

`tools/list` advertises `readOnlyHint: true` on the 39 read-only tools and
`readOnlyHint: false` + `destructiveHint: true` on the 25 mutating tools, so the gateway
hides mutating tools from read-only groups. The full tool set (64 tools) is unchanged by
this deployment adaptation.

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

This server registers itself as `"nx-witness"`. All tools appear in Claude Code under the `mcp__nx-witness__` prefix (e.g. `mcp__nx-witness__nx_read_list_cameras`).

Some NX Witness installations also expose a built-in MCP connector (sometimes listed as `"NXWitness"` or `"nx-meta"` in Claude Code's connector settings). If both this server and a built-in connector are registered simultaneously, the tools appear in **two independent namespaces** with **independent permission settings** — which can cause confusion about which namespace to use or why enabling one doesn't affect the other.

**Recommendation:** Use only one MCP integration at a time. For full tool coverage and multi-system support, use this server exclusively and remove or disable any other NX Witness connectors.

---

## Available Tools

| Category | Tools |
|----------|-------|
| Systems | `nx_read_list_systems`, `nx_read_server_info`, `nx_read_list_servers` |
| Cameras & Devices | `nx_read_list_cameras`, `nx_read_get_camera`, `nx_write_create_device`, `nx_update_replace_device`, `nx_update_modify_device`, `nx_delete_device`, `nx_read_get_device_status`, `nx_read_get_device_io`, `nx_update_set_device_io`, `nx_read_camera_snapshot`, `nx_read_camera_stream_url` |
| Device Search | `nx_read_list_device_searches`, `nx_write_start_device_search`, `nx_read_get_device_search`, `nx_delete_stop_device_search`, `nx_read_get_device_types`, `nx_read_get_device_diagnosis`, `nx_read_get_all_devices_diagnosis` |
| Recording | `nx_read_get_footage` |
| PTZ | `nx_read_ptz_get_position`, `nx_write_ptz_set_position`, `nx_write_ptz_move`, `nx_delete_ptz_stop`, `nx_read_ptz_get_presets`, `nx_write_ptz_activate_preset` |
| Storage | `nx_read_list_storages`, `nx_read_get_storage_status` |
| Users | `nx_read_list_users` |
| Bookmarks | `nx_read_list_bookmarks`, `nx_read_get_bookmark`, `nx_write_create_bookmark`, `nx_update_bookmark`, `nx_delete_bookmark` |
| Events | `nx_read_get_events`, `nx_read_get_event_manifest_events`, `nx_read_get_event_manifest_actions` |
| Acknowledges | `nx_read_get_acknowledges`, `nx_write_acknowledge_event`, `nx_read_get_acknowledge` |
| Triggers | `nx_read_get_triggers`, `nx_read_get_trigger`, `nx_write_fire_trigger` |
| Rules | `nx_read_get_rules`, `nx_read_get_rule`, `nx_write_create_rule`, `nx_update_replace_rule`, `nx_update_modify_rule`, `nx_delete_rule`, `nx_write_reset_rules` |
| Generic Events | `nx_write_create_generic_event` |
| Analytics & Integrations | `nx_read_list_analytics_engines`, `nx_read_list_integrations`, `nx_read_get_integration`, `nx_delete_analytics_integration` |
| Virtual Uploads | `nx_read_virtual_list_uploads`, `nx_write_virtual_start_upload`, `nx_read_virtual_get_transfer_status`, `nx_delete_virtual_cancel_upload` |
| Logs & Audit | `nx_read_get_log_settings`, `nx_read_get_server_log`, `nx_read_get_audit_log` |
| Software Updates | `nx_read_get_build_info`, `nx_read_get_build_status`, `nx_read_get_build_storage_servers`, `nx_write_start_build_download`, `nx_write_install_build`, `nx_write_finish_build_update`, `nx_write_retry_build_update`, `nx_delete_cancel_build_update` |

### Software Updates

These tools drive the same upgrade flow as Nx Desktop's **Updates** tab, per site:

1. `nx_read_get_build_info` with `info_category="installed"` — which build the site runs today.
2. `nx_read_get_build_info` with `info_category="latest"` — what it could upgrade to.
3. `nx_write_start_build_download` — downloads the build to every server in the site. It resolves
   the update manifest automatically; pass `version` to pin a specific build, or `manifest` to
   supply one from step 2 verbatim.
4. `nx_read_get_build_status` — poll until every server reports `readyToInstall`.
5. `nx_write_install_build` — install on explicit server UUIDs (from `nx_read_list_servers`).
   There is no install-everywhere default. **Each server restarts its media server service,
   so recording and live view drop briefly.**
6. `nx_write_finish_build_update` — close out the upgrade.

`nx_write_retry_build_update` retries a step that failed (e.g. `noFreeSpaceToDownload`), and
`nx_delete_cancel_build_update` aborts an in-progress update, clearing the manifest and stopping
downloads — it does not roll back servers that already installed.

Notes:

- This is the **v4 `Update` API family — Nx 6.x and newer**. Older servers return 404.
- Everything except `nx_read_get_build_info` and `nx_read_get_build_status` requires a
  **Power User** on the site; a 403 means the MCP credential is under-privileged.
- The tools are named around `build` rather than `update` on purpose: the TWG MCP Control Plane's
  tool-contract inspector reads a mutating verb in a read-only tool's *name* as evidence it
  mutates (see the `nx_read_virtual_get_transfer_status` rename in the changelog).

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

See [CHANGELOG.md](CHANGELOG.md) for the full version history.

### v2.2.0 (2026-07-14)
- Added per-site env vars `NX_SYSTEM_<NAME>_HOST`/`_USER`/`_PASS` for multi-system config, and fixed multi-system deployments that used them being silently ignored (the server had no parser and fell back to the single-system default). See [Multiple systems](#multiple-systems).

### v2.1.0 (2026-07-13)
- Control-plane deployment: honor the injected `PORT`, add `GET /healthz`, per-tool JSON logging, `destructiveHint` annotations on mutating tools, and the `NX_SYSTEMS` JSON env var for multi-system config.

### v2.0.1 (2026-04-01)
- Fixed `SyntaxError: non-default argument follows default argument` on import — `system: SYS` is now the first parameter in all 18 affected tool functions.

### v2.0.0 (2026-04-01) — Breaking change
- **`system` is now required** on all tools. Call `nx_read_list_systems` first to get available system names, then pass a system name to every subsequent tool call. This fixes a discoverability issue where Claude Desktop silently omitted the optional parameter and only queried the default system.
