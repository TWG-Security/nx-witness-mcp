"""ASGI middleware that aligns FastMCP Streamable HTTP transport behavior
with the TypeScript @modelcontextprotocol/sdk:

  - Handles OPTIONS (CORS preflight) with 204 No Content
  - Normalizes error responses to match TypeScript SDK format:
      GET (no session) → 400 plain text "No sessionId"
      DELETE 404 → 400 plain text "No active transport"
      POST 406 → JSON with id: null (not id: "server-error")
  - Injects id: fields into SSE events (required for Last-Event-ID reconnection
    and message tracking by some MCP clients)
  - Converts hex session IDs to UUID format
  - Strips the extra 'no-transform' directive from Cache-Control
"""

import time
import uuid


class MCPTransportMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # CORS preflight — must return 204 before FastMCP sees the request
        if scope["method"] == "OPTIONS":
            await send({"type": "http.response.start", "status": 204, "headers": []})
            await send({"type": "http.response.body", "body": b""})
            return

        # GET without mcp-session-id — FastMCP would 406 on Accept-header validation
        # before reaching the session check; short-circuit to match CW's 400 response
        if scope["method"] == "GET":
            req_headers = {k.lower(): v for k, v in scope.get("headers", [])}
            if b"mcp-session-id" not in req_headers:
                await send({"type": "http.response.start", "status": 400,
                            "headers": _plain_text_headers()})
                await send({"type": "http.response.body", "body": b"No sessionId"})
                return

        # Normalize mcp-session-id from UUID format back to hex for FastMCP lookup
        scope = {**scope, "headers": _patch_request_headers(scope.get("headers", []))}

        method = scope["method"]
        state = {
            "is_sse": False,
            "session_id": None,
            "counter": 0,
            "buf": b"",
            "status": None,
            "deferred_start": None,
        }

        async def patched_send(message):
            if message["type"] == "http.response.start":
                headers, is_sse, sid = _patch_headers(message.get("headers", []))
                state["is_sse"] = is_sse
                state["session_id"] = sid or str(uuid.uuid4())
                state["status"] = message["status"]
                patched = {**message, "headers": headers}
                if is_sse:
                    # SSE: forward immediately so the client sees headers right away
                    await send(patched)
                else:
                    # Buffer; we may need to rewrite status/headers/body together
                    state["deferred_start"] = patched

            elif message["type"] == "http.response.body" and state["is_sse"]:
                data = state["buf"] + message.get("body", b"")
                more = message.get("more_body", False)
                out, state["buf"] = _inject_ids(
                    data, state["session_id"], state["counter"], flush=not more
                )
                state["counter"] += out.count(b"\n\n")
                await send({**message, "body": out})

            elif message["type"] == "http.response.body":
                status = state["status"]
                body = message.get("body", b"")
                start = state["deferred_start"]

                if method == "DELETE" and status == 404:
                    start = {**start, "status": 400, "headers": _plain_text_headers()}
                    body = b"No active transport"
                elif method == "POST" and status == 406:
                    body = _fix_406_body(body)

                if start:
                    await send(start)
                await send({**message, "body": body})

            else:
                await send(message)

        await self.app(scope, receive, patched_send)


def _plain_text_headers():
    return [(b"content-type", b"text/plain")]


def _fix_406_body(body: bytes) -> bytes:
    # Replace "server-error" value with null in the JSON-RPC id field.
    # Handles both compact ("id":"server-error") and spaced ("id": "server-error") forms.
    return body.replace(b'"server-error"', b"null")


def _patch_headers(raw_headers):
    result, is_sse, session_id = [], False, None
    for name, value in raw_headers:
        lname = name.lower()
        if lname == b"mcp-session-id":
            session_id = _hex_to_uuid(value.decode())
            result.append((name, session_id.encode()))
        elif lname == b"cache-control":
            cleaned = (
                value.decode()
                .replace(", no-transform", "")
                .replace("no-transform, ", "")
                .replace("no-transform", "")
                .strip(", ")
            )
            result.append((name, cleaned.encode()))
        else:
            if lname == b"content-type" and b"text/event-stream" in value:
                is_sse = True
            result.append((name, value))
    return result, is_sse, session_id


def _patch_request_headers(raw_headers):
    """Strip UUID dashes from mcp-session-id so FastMCP sees its original hex format."""
    result = []
    for name, value in raw_headers:
        if name.lower() == b"mcp-session-id":
            result.append((name, value.decode().replace("-", "").encode()))
        else:
            result.append((name, value))
    return result


def _hex_to_uuid(hex_str: str) -> str:
    clean = hex_str.replace("-", "")[:32].ljust(32, "0")
    return f"{clean[0:8]}-{clean[8:12]}-{clean[12:16]}-{clean[16:20]}-{clean[20:32]}"


def _inject_ids(body: bytes, session_id: str, counter: int, flush: bool):
    parts = body.split(b"\n\n")
    complete, remaining = parts[:-1], parts[-1]
    if flush and remaining.strip():
        complete.append(remaining)
        remaining = b""
    out = []
    for i, event in enumerate(complete):
        if event.strip() and b"id:" not in event:
            ts = int(time.time() * 1000)
            eid = f"{session_id}_{ts}_{counter + i:04d}_000"
            event = _insert_id(event, eid)
        out.append(event)
    return b"\n\n".join(out) + (b"\n\n" if out else b""), remaining


def _insert_id(event: bytes, event_id: str) -> bytes:
    id_line = f"id: {event_id}".encode()
    if event.startswith(b"event:"):
        pos = event.find(b"\n")
        if pos != -1:
            return event[: pos + 1] + id_line + b"\n" + event[pos + 1 :]
    return id_line + b"\n" + event
