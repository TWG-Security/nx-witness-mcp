"""NX Witness API client."""

import re
from typing import Any
import httpx

# Nx Cloud relay hosts embed the site's cloud id: https://{cloudId}.relay[-region].vmsproxy.com
_RELAY_HOST = re.compile(r"^https?://([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.relay[\w-]*\.vmsproxy\.com", re.I)


class NXClient:
    def __init__(self, host: str, username: str, password: str):
        self.base_url = host.rstrip("/")
        self.username = username
        self.password = password
        self._token: str | None = None
        self._site_info: dict | None = None
        self._client = httpx.AsyncClient(verify=False, follow_redirects=True)

    async def _login(self) -> None:
        login_path = "/rest/v3/login/sessions"
        r = await self._client.post(
            f"{self.base_url}{login_path}",
            json={"username": self.username, "password": self.password},
        )
        r.raise_for_status()
        self._token = r.json()["token"]
        # NX Cloud relay hosts (*.relay.vmsproxy.com) 307-redirect to a
        # region-specific node (e.g. *.relay-us-nyc-2-prod-dp.vmsproxy.com).
        # Pin base_url to the post-redirect origin so subsequent authenticated
        # requests aren't redirected — httpx strips the Authorization header
        # on cross-origin redirects (RFC 7235 safety), producing 401.
        final = str(r.url)
        if final.endswith(login_path):
            self.base_url = final[: -len(login_path)]

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._token}"}

    async def _request(self, method: str, path: str, params: dict | None = None, body: Any = None) -> Any:
        if not self._token:
            await self._login()
        url = f"{self.base_url}{path}"
        kwargs: dict[str, Any] = {"headers": self._headers()}
        if params:
            kwargs["params"] = params
        if body is not None:
            kwargs["json"] = body
        r = await self._client.request(method, url, **kwargs)
        if r.status_code == 401:
            await self._login()
            kwargs["headers"] = self._headers()
            r = await self._client.request(method, url, **kwargs)
        r.raise_for_status()
        if not r.content:
            return {}
        return r.json()

    async def _get_bytes(self, path: str, params: dict | None = None) -> bytes:
        if not self._token:
            await self._login()
        url = f"{self.base_url}{path}"
        r = await self._client.get(url, headers=self._headers(), params=params)
        if r.status_code == 401:
            await self._login()
            r = await self._client.get(url, headers=self._headers(), params=params)
        r.raise_for_status()
        return r.content

    async def _get_text(self, path: str, params: dict | None = None) -> str:
        if not self._token:
            await self._login()
        url = f"{self.base_url}{path}"
        r = await self._client.get(url, headers=self._headers(), params=params)
        if r.status_code == 401:
            await self._login()
            r = await self._client.get(url, headers=self._headers(), params=params)
        r.raise_for_status()
        return r.text

    # Convenience wrappers
    async def _get(self, path: str, params: dict | None = None) -> Any:
        return await self._request("GET", path, params=params)

    async def _post(self, path: str, body: Any = None) -> Any:
        return await self._request("POST", path, body=body or {})

    async def _put(self, path: str, body: Any = None) -> Any:
        return await self._request("PUT", path, body=body or {})

    async def _patch(self, path: str, body: Any = None) -> Any:
        return await self._request("PATCH", path, body=body or {})

    async def _delete(self, path: str) -> Any:
        return await self._request("DELETE", path)

    # -------------------------------------------------------------------------
    # Servers & Devices
    # -------------------------------------------------------------------------

    async def get_server_info(self) -> dict:
        servers = await self._get("/rest/v4/servers")
        return servers[0] if servers else {}

    async def list_devices(self, device_type: str | None = None) -> list[dict]:
        params = {}
        if device_type:
            params["deviceType"] = device_type
        return await self._get("/rest/v4/devices", params=params or None)

    async def get_device(self, device_id: str) -> dict:
        return await self._get(f"/rest/v4/devices/{device_id}")

    async def get_camera_snapshot(self, device_id: str, width: int | None = None, height: int | None = None) -> bytes:
        """Returns raw JPEG bytes."""
        ticket_resp = await self._post("/rest/v4/login/tickets")
        ticket = ticket_resp.get("token") or ticket_resp.get("ticket") or ""
        if isinstance(ticket, dict):
            ticket = ticket.get("token") or ticket.get("ticket", "")
        params: dict[str, Any] = {"_ticket": ticket}
        if width:
            params["width"] = width
        if height:
            params["height"] = height
        return await self._get_bytes(f"/rest/v4/devices/{device_id}/image", params=params)

    async def get_camera_stream_url(self, device_id: str) -> str:
        ticket_resp = await self._post("/rest/v4/login/tickets")
        ticket = ticket_resp.get("token") or ticket_resp.get("ticket") or ""
        if isinstance(ticket, dict):
            ticket = ticket.get("token") or ticket.get("ticket", "")
        return f"{self.base_url}/rest/v4/devices/{device_id}/media?_ticket={ticket}"

    # -------------------------------------------------------------------------
    # Events - Log
    # -------------------------------------------------------------------------

    async def get_events(
        self,
        limit: int = 50,
        event_type: str | None = None,
        event_subtype: str | None = None,
        action_type: str | None = None,
        device_id: str | None = None,
        rule_id: str | None = None,
        text: str | None = None,
        flags: str | None = None,
        from_ms: int | None = None,
        duration_ms: int | None = None,
        descending: bool = True,
        server_id: str | None = None,
    ) -> list[dict]:
        params: dict[str, Any] = {"limit": limit}
        if descending:
            params["order"] = "desc"
        if event_type:
            params["eventType"] = event_type
        if event_subtype:
            params["eventSubtype"] = event_subtype
        if action_type:
            params["actionType"] = action_type
        if device_id:
            params["eventResourceId"] = device_id
        if rule_id:
            params["ruleId"] = rule_id
        if text:
            params["text"] = text
        if flags:
            params["flags"] = flags
        if from_ms:
            params["startTimeMs"] = from_ms
        if duration_ms:
            params["durationMs"] = duration_ms
        path = f"/rest/v4/events/log/{server_id}" if server_id else "/rest/v4/events/log"
        return await self._get(path, params=params)

    # -------------------------------------------------------------------------
    # Events - Manifest
    # -------------------------------------------------------------------------

    async def get_event_manifest_events(self) -> Any:
        return await self._get("/rest/v4/events/manifest/events")

    async def get_event_manifest_actions(self) -> Any:
        return await self._get("/rest/v4/events/manifest/actions")

    # -------------------------------------------------------------------------
    # Events - Acknowledges
    # -------------------------------------------------------------------------

    async def get_acknowledges(self) -> Any:
        return await self._get("/rest/v4/events/acknowledges")

    async def acknowledge_event(self, device_id: str, action_id: str, action_server_id: str,
                                start_time_ms: int, duration_ms: int = 1000, name: str = "Bookmark") -> Any:
        body = {
            "deviceId": device_id,
            "actionId": action_id,
            "actionServerId": action_server_id,
            "startTimeMs": start_time_ms,
            "durationMs": duration_ms,
            "name": name,
        }
        return await self._post("/rest/v4/events/acknowledges", body=body)

    async def get_acknowledge(self, ack_id: str) -> Any:
        return await self._get(f"/rest/v4/events/acknowledges/{ack_id}")

    # -------------------------------------------------------------------------
    # Events - Generic
    # -------------------------------------------------------------------------

    async def create_generic_event(
        self,
        source: str,
        caption: str | None = None,
        description: str | None = None,
        metadata: dict | None = None,
        state: str = "instant",
    ) -> Any:
        body: dict[str, Any] = {"source": source, "state": state}
        if caption:
            body["caption"] = caption
        if description:
            body["description"] = description
        if metadata:
            body["metadata"] = metadata
        return await self._post("/rest/v4/events/generic", body=body)

    # -------------------------------------------------------------------------
    # Events - Soft Triggers
    # -------------------------------------------------------------------------

    async def get_triggers(self) -> Any:
        return await self._get("/rest/v4/events/triggers")

    async def get_trigger(self, trigger_id: str) -> Any:
        return await self._get(f"/rest/v4/events/triggers/{trigger_id}")

    async def fire_trigger(self, trigger_id: str, device_id: str | None = None, state: str = "started") -> Any:
        body: dict[str, Any] = {"triggerId": trigger_id, "state": state}
        if device_id:
            body["deviceId"] = device_id
        return await self._post("/rest/v4/events/triggers", body=body)

    # -------------------------------------------------------------------------
    # Events - Rules
    # -------------------------------------------------------------------------

    async def get_rules(self) -> Any:
        return await self._get("/rest/v4/events/rules")

    async def get_rule(self, rule_id: str) -> Any:
        return await self._get(f"/rest/v4/events/rules/{rule_id}")

    async def create_rule(self, rule: dict) -> Any:
        return await self._post("/rest/v4/events/rules", body=rule)

    async def replace_rule(self, rule_id: str, rule: dict) -> Any:
        return await self._put(f"/rest/v4/events/rules/{rule_id}", body=rule)

    async def modify_rule(self, rule_id: str, changes: dict) -> Any:
        return await self._patch(f"/rest/v4/events/rules/{rule_id}", body=changes)

    async def delete_rule(self, rule_id: str) -> Any:
        return await self._delete(f"/rest/v4/events/rules/{rule_id}")

    async def reset_rules(self) -> Any:
        return await self._post("/rest/v4/events/rules/*/reset")

    # -------------------------------------------------------------------------
    # Analytics & Users
    # -------------------------------------------------------------------------

    async def list_analytics_engines(self) -> list[dict]:
        return await self._get("/rest/v4/analytics/engines")

    async def list_users(self) -> list[dict]:
        return await self._get("/rest/v4/users")

    # -------------------------------------------------------------------------
    # Servers - Extended
    # -------------------------------------------------------------------------

    async def list_servers(self) -> list[dict]:
        return await self._get("/rest/v4/servers")

    async def list_storages(self, server_id: str) -> list[dict]:
        return await self._get(f"/rest/v4/servers/{server_id}/storages")

    async def get_storage_status(self, server_id: str, storage_id: str) -> dict:
        return await self._get(f"/rest/v4/servers/{server_id}/storages/{storage_id}/status")

    # -------------------------------------------------------------------------
    # Bookmarks
    # -------------------------------------------------------------------------

    async def list_bookmarks(
        self,
        device_id: str,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
        text: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        params: dict[str, Any] = {}
        if start_time_ms is not None:
            params["startTimeMs"] = start_time_ms
        if end_time_ms is not None:
            params["endTimeMs"] = end_time_ms
        if text:
            params["text"] = text
        if limit is not None:
            params["limit"] = limit
        return await self._get(f"/rest/v4/devices/{device_id}/bookmarks", params=params or None)

    async def create_bookmark(
        self,
        device_id: str,
        name: str,
        duration_ms: int,
        start_time_ms: int | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
    ) -> dict:
        body: dict[str, Any] = {"name": name, "durationMs": duration_ms}
        if start_time_ms is not None:
            body["startTimeMs"] = start_time_ms
        if description:
            body["description"] = description
        if tags:
            body["tags"] = tags
        return await self._post(f"/rest/v4/devices/{device_id}/bookmarks", body=body)

    async def get_bookmark(self, device_id: str, bookmark_id: str) -> dict:
        return await self._get(f"/rest/v4/devices/{device_id}/bookmarks/{bookmark_id}")

    async def update_bookmark(
        self,
        device_id: str,
        bookmark_id: str,
        name: str | None = None,
        description: str | None = None,
        start_time_ms: int | None = None,
        duration_ms: int | None = None,
        tags: list[str] | None = None,
    ) -> dict:
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if description is not None:
            body["description"] = description
        if start_time_ms is not None:
            body["startTimeMs"] = start_time_ms
        if duration_ms is not None:
            body["durationMs"] = duration_ms
        if tags is not None:
            body["tags"] = tags
        return await self._patch(f"/rest/v4/devices/{device_id}/bookmarks/{bookmark_id}", body=body)

    async def delete_bookmark(self, bookmark_id: str) -> Any:
        return await self._delete(f"/rest/v4/devices/*/bookmarks/{bookmark_id}")

    # -------------------------------------------------------------------------
    # Footage
    # -------------------------------------------------------------------------

    async def get_footage(
        self,
        device_id: str,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
        detail_level_ms: int | None = None,
        max_count: int | None = None,
    ) -> Any:
        params: dict[str, Any] = {}
        if start_time_ms is not None:
            params["startTimeMs"] = start_time_ms
        if end_time_ms is not None:
            params["endTimeMs"] = end_time_ms
        if detail_level_ms is not None:
            params["detailLevelMs"] = detail_level_ms
        if max_count is not None:
            params["maxCount"] = max_count
        return await self._get(f"/rest/v4/devices/{device_id}/footage", params=params or None)

    # -------------------------------------------------------------------------
    # PTZ Control
    # -------------------------------------------------------------------------

    async def ptz_get_position(self, device_id: str) -> dict:
        return await self._get(f"/rest/v4/devices/{device_id}/ptz/position")

    async def ptz_set_position(
        self,
        device_id: str,
        speed: float,
        pan: float | None = None,
        tilt: float | None = None,
        zoom: float | None = None,
    ) -> dict:
        body: dict[str, Any] = {"speed": speed}
        if pan is not None:
            body["pan"] = pan
        if tilt is not None:
            body["tilt"] = tilt
        if zoom is not None:
            body["zoom"] = zoom
        return await self._post(f"/rest/v4/devices/{device_id}/ptz/position", body=body)

    async def ptz_move(
        self,
        device_id: str,
        pan: float | None = None,
        tilt: float | None = None,
        zoom: float | None = None,
        focus: float | None = None,
    ) -> Any:
        body: dict[str, Any] = {}
        if pan is not None:
            body["pan"] = pan
        if tilt is not None:
            body["tilt"] = tilt
        if zoom is not None:
            body["zoom"] = zoom
        if focus is not None:
            body["focus"] = focus
        return await self._post(f"/rest/v4/devices/{device_id}/ptz/move", body=body)

    async def ptz_stop(self, device_id: str) -> Any:
        return await self._delete(f"/rest/v4/devices/{device_id}/ptz/move")

    async def ptz_get_presets(self, device_id: str) -> Any:
        return await self._get(f"/rest/v4/devices/{device_id}/ptz/presets")

    async def ptz_activate_preset(self, device_id: str, preset_id: str, speed: float = 0.5) -> Any:
        return await self._post(
            f"/rest/v4/devices/{device_id}/ptz/presets/{preset_id}/activate",
            body={"speed": speed},
        )

    # -------------------------------------------------------------------------
    # Device IO & Status
    # -------------------------------------------------------------------------

    async def get_device_io(self, device_id: str) -> Any:
        return await self._get(f"/rest/v4/devices/{device_id}/io")

    async def set_device_io(self, device_id: str, ports: dict) -> Any:
        return await self._patch(f"/rest/v4/devices/{device_id}/io", body={"ports": ports})

    async def get_device_status(self, device_id: str) -> dict:
        return await self._get(f"/rest/v4/devices/{device_id}/status")

    async def create_device(
        self,
        physical_id: str,
        url: str,
        type_id: str,
        name: str | None = None,
        server_id: str | None = None,
        mac: str | None = None,
        credentials: dict | None = None,
        parameters: dict | None = None,
        group: dict | None = None,
        options: dict | None = None,
        schedule: dict | None = None,
        motion: dict | None = None,
    ) -> dict:
        body: dict[str, Any] = {
            "physicalId": physical_id,
            "url": url,
            "typeId": type_id,
        }
        if name is not None:
            body["name"] = name
        if server_id is not None:
            body["serverId"] = server_id
        if mac is not None:
            body["mac"] = mac
        if credentials is not None:
            body["credentials"] = credentials
        if parameters is not None:
            body["parameters"] = parameters
        if group is not None:
            body["group"] = group
        if options is not None:
            body["options"] = options
        if schedule is not None:
            body["schedule"] = schedule
        if motion is not None:
            body["motion"] = motion
        return await self._post("/rest/v4/devices", body=body)

    async def replace_device(self, device_id: str, device: dict) -> dict:
        return await self._put(f"/rest/v4/devices/{device_id}", body=device)

    async def modify_device(self, device_id: str, changes: dict) -> dict:
        return await self._patch(f"/rest/v4/devices/{device_id}", body=changes)

    async def delete_device(self, device_id: str) -> Any:
        return await self._delete(f"/rest/v4/devices/{device_id}")

    async def get_device_types(self) -> list[dict]:
        return await self._get("/rest/v4/devices/*/types")

    async def start_device_search(
        self,
        target: dict,
        port: int | None = None,
        credentials: dict | None = None,
        mode: str | None = None,
        server_id: str | None = None,
    ) -> dict:
        body: dict[str, Any] = {"target": target}
        if port is not None:
            body["port"] = port
        if credentials is not None:
            body["credentials"] = credentials
        if mode is not None:
            body["mode"] = mode
        if server_id is not None:
            body["serverId"] = server_id
        return await self._post("/rest/v4/devices/*/searches", body=body)

    async def list_device_searches(self) -> list[dict]:
        return await self._get("/rest/v4/devices/*/searches")

    async def get_device_search(self, search_id: str) -> dict:
        return await self._get(f"/rest/v4/devices/*/searches/{search_id}")

    async def stop_device_search(self, search_id: str) -> Any:
        return await self._delete(f"/rest/v4/devices/*/searches/{search_id}")

    async def get_all_devices_diagnosis(self) -> list[dict]:
        return await self._get("/rest/v4/devices/*/status")

    # -------------------------------------------------------------------------
    # Virtual Device Uploads (v4, added in 6.1.1)
    # -------------------------------------------------------------------------

    async def virtual_list_uploads(self, device_id: str) -> list[dict]:
        return await self._get(f"/rest/v4/devices/{device_id}/virtual/uploads")

    async def virtual_start_upload(self, device_id: str, files: list[dict]) -> Any:
        """Initiate one or more file uploads.
        Each file dict: startTimeMs, durationMs, sizeB, md5, container, codec.
        Returns upload session details including uploadId, chunkSizeB, fileId.
        """
        return await self._post(f"/rest/v4/devices/{device_id}/virtual/uploads", body=files)

    async def virtual_get_upload_status(self, device_id: str, upload_id: str) -> dict:
        return await self._get(f"/rest/v4/devices/{device_id}/virtual/uploads/{upload_id}")

    async def virtual_cancel_upload(self, device_id: str, upload_id: str) -> Any:
        return await self._delete(f"/rest/v4/devices/{device_id}/virtual/uploads/{upload_id}")

    # -------------------------------------------------------------------------
    # Analytics Integrations (DELETE now functional in 6.1.1)
    # -------------------------------------------------------------------------

    async def list_integrations(self) -> list[dict]:
        return await self._get("/rest/v4/integrations")

    async def get_integration(self, integration_id: str) -> dict:
        return await self._get(f"/rest/v4/integrations/{integration_id}")

    async def delete_analytics_integration(self, integration_id: str) -> Any:
        return await self._delete(f"/rest/v4/analytics/integrations/{integration_id}")

    # -------------------------------------------------------------------------
    # Analytics Object Search (object tracks in the Analytics DB)
    # -------------------------------------------------------------------------

    async def search_object_tracks(
        self,
        device_ids: list[str] | None = None,
        object_type_ids: list[str] | None = None,
        free_text: str | None = None,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
        bounding_box: str | None = None,
        analytics_engine_id: str | None = None,
        limit: int | None = None,
        sort_order: str | None = None,
    ) -> list[dict]:
        # List values are sent as repeated query params (deviceId=a&deviceId=b).
        params: dict[str, Any] = {}
        if device_ids:
            params["deviceId"] = device_ids
        if object_type_ids:
            params["objectTypeId"] = object_type_ids
        if free_text:
            params["freeText"] = free_text
        if start_time_ms is not None:
            params["startTimeMs"] = start_time_ms
        if end_time_ms is not None:
            params["endTimeMs"] = end_time_ms
        if bounding_box:
            params["boundingBox"] = bounding_box
        if analytics_engine_id:
            params["analyticsEngineId"] = analytics_engine_id
        if limit is not None:
            params["limit"] = limit
        if sort_order:
            params["sortOrder"] = sort_order
        return await self._get("/rest/v4/analytics/objectTracks", params=params or None)

    async def collect_object_tracks(self, max_tracks: int, page_size: int = 1000, **filters: Any) -> tuple[list[dict], bool]:
        """Fetch up to max_tracks tracks, newest first, paging backwards in time.

        The API has `limit` but no offset, so each page narrows endTimeMs to the
        oldest start seen so far. Tracks straddling the boundary come back again
        and are de-duplicated by id. Returns (tracks, truncated).
        """
        seen: dict[str, dict] = {}
        end_ms = filters.pop("end_time_ms", None)
        while True:
            # Always ask for a full page: a short request could be filled entirely by
            # boundary duplicates and end the scan early.
            page = await self.search_object_tracks(
                **filters, end_time_ms=end_ms, limit=page_size, sort_order="desc"
            ) or []
            new = [t for t in page if t.get("id") not in seen]
            room = max_tracks - len(seen)
            for t in new[:room]:
                seen[t.get("id")] = t
            if len(page) < page_size:
                return list(seen.values()), len(new) > room
            if len(seen) >= max_tracks or not new:
                # Cap reached, or more than page_size tracks share one start time.
                return list(seen.values()), True
            end_ms = min(int(t["startTimeMs"]) for t in page)

    def relay_cloud_id(self) -> str | None:
        """Cloud id parsed from a relay host URL, or None for LAN/Tailscale hosts."""
        m = _RELAY_HOST.match(self.base_url)
        return m.group(1).lower() if m else None

    async def get_site_info(self) -> dict:
        """GET /rest/v4/site/info — cached; ids and cloud binding don't change at runtime.

        If the call fails (older server, restricted user) on a relay-configured site,
        fall back to the cloud id embedded in the host so links still work.
        """
        if self._site_info is None:
            try:
                self._site_info = await self._get("/rest/v4/site/info")
            except httpx.HTTPStatusError:
                cloud_id = self.relay_cloud_id()
                if not cloud_id:
                    raise
                self._site_info = {"cloudId": cloud_id, "cloudHost": "nxvms.com"}
        return self._site_info

    async def get_object_track(self, track_id: str) -> dict:
        return await self._get(f"/rest/v4/analytics/objectTracks/{track_id}")

    async def get_object_track_best_shot(self, track_id: str, device_id: str) -> bytes:
        """Returns the track's Best Shot as raw JPEG bytes (server converts to jpg)."""
        return await self._get_bytes(
            f"/rest/v4/analytics/objectTracks/{track_id}/bestShotImage.jpg",
            params={"deviceId": device_id},
        )

    # -------------------------------------------------------------------------
    # Server Logs
    # -------------------------------------------------------------------------

    async def get_log_settings(self, server_id: str = "this") -> dict:
        return await self._get(f"/rest/v2/servers/{server_id}/logSettings")

    async def get_server_log(self, name: str = "MAIN", lines: int = 200) -> str:
        return await self._get_text("/api/showLog", params={"name": name, "lines": lines})

    # -------------------------------------------------------------------------
    # Audit Log
    # -------------------------------------------------------------------------

    async def get_audit_log(
        self,
        limit: int = 50,
        event_type: str | None = None,
        username: str | None = None,
        from_sec: int | None = None,
        to_sec: int | None = None,
    ) -> list[dict]:
        entries: list[dict] = (await self._get("/api/auditLog")).get("reply", [])
        if event_type:
            entries = [e for e in entries if e.get("eventType") == event_type]
        if username:
            entries = [e for e in entries if e.get("authSession", {}).get("userName", "").lower() == username.lower()]
        if from_sec is not None:
            entries = [e for e in entries if e.get("createdTimeSec", 0) >= from_sec]
        if to_sec is not None:
            entries = [e for e in entries if e.get("createdTimeSec", 0) <= to_sec]
        # Sort most recent first
        entries.sort(key=lambda e: e.get("createdTimeSec", 0), reverse=True)
        return entries[:limit]

    # -------------------------------------------------------------------------
    # Software Updates (v4 "Update" section; Nx 6.x and newer)
    # -------------------------------------------------------------------------

    async def get_update_info(
        self,
        info_category: str | None = None,
        version: str | None = None,
        publication_type: str | None = None,
        update_component: str | None = None,
    ) -> dict:
        """Update manifest for a build. This is the body POST /update/start expects."""
        params: dict[str, Any] = {}
        if info_category:
            params["infoCategory"] = info_category
        if version:
            params["version"] = version
        if publication_type:
            params["publicationType"] = publication_type
        if update_component:
            params["updateComponent"] = update_component
        return await self._get("/rest/v4/update/info", params=params or None)

    async def get_update_status(self) -> dict:
        """Site-wide update state, keyed by server id."""
        return await self._get("/rest/v4/update")

    async def get_update_storage(self, info_category: str = "target") -> dict:
        return await self._get(f"/rest/v4/update/storage/{info_category}")

    async def start_update(self, manifest: dict) -> dict:
        """Begin downloading a build. `manifest` comes from get_update_info()."""
        return await self._post("/rest/v4/update/start", body=manifest)

    async def install_update(self, peers: list[str]) -> Any:
        return await self._post("/rest/v4/update/install", body={"peers": peers})

    async def finish_update(self, ignore_pending_peers: bool | None = None) -> Any:
        body: dict[str, Any] = {}
        if ignore_pending_peers is not None:
            body["ignorePendingPeers"] = ignore_pending_peers
        return await self._post("/rest/v4/update/finish", body=body)

    async def retry_update(self) -> dict:
        return await self._post("/rest/v4/update/retry")

    async def cancel_update(self) -> Any:
        return await self._delete("/rest/v4/update")

    async def close(self) -> None:
        await self._client.aclose()
