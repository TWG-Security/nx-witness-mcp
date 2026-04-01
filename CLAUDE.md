# MCP Server Development Notes

## Lesson: Session ID Transformation Must Be Symmetric

### The Bug (fixed 2026-04-01)

FastMCP generates session IDs as hex strings without dashes:
```
a1b2c3d4e5f678901234567890abcdef
```

The middleware (`middleware.py`) was converting them to UUID format in **responses**:
```
a1b2c3d4-e5f6-7890-1234-567890abcdef
```

But it was NOT converting them back on **incoming requests**. So the client sent back the UUID, FastMCP looked it up by UUID, found nothing (it stored it as hex), and the session failed.

### The Rule

Any middleware that transforms a session ID must do it in **both directions**:

| Direction | Transform |
|-----------|-----------|
| Response (outbound) | Internal format → Client format (hex → UUID) |
| Request (inbound) | Client format → Internal format (UUID → hex) |

See `_patch_request_headers()` (strips dashes) and `_patch_headers()` / `_hex_to_uuid()` (adds dashes) in `middleware.py`.

### Quick Sanity Test for Any MCP Build

1. Send an initial POST to establish a session — note the `mcp-session-id` in the response
2. Immediately send a GET with that exact session ID value
3. If you get a session-not-found error, you have a one-way transform bug
