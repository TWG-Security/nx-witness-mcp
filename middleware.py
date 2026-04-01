"""ASGI middleware that aligns FastMCP Streamable HTTP transport behavior
with the TypeScript @modelcontextprotocol/sdk:

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

        state = {"is_sse": False, "session_id": None, "counter": 0, "buf": b""}

        async def patched_send(message):
            if message["type"] == "http.response.start":
                headers, is_sse, sid = _patch_headers(message.get("headers", []))
                state["is_sse"] = is_sse
                state["session_id"] = sid or str(uuid.uuid4())
                await send({**message, "headers": headers})

            elif message["type"] == "http.response.body" and state["is_sse"]:
                data = state["buf"] + message.get("body", b"")
                more = message.get("more_body", False)
                out, state["buf"] = _inject_ids(
                    data, state["session_id"], state["counter"], flush=not more
                )
                state["counter"] += out.count(b"\n\n")
                await send({**message, "body": out})

            else:
                await send(message)

        await self.app(scope, receive, patched_send)


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
