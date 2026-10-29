"""Read-only Gitee MCP protocol diagnostics; no credential or response output."""

import argparse
import asyncio
import json
import logging
from pathlib import Path
import sys
from typing import get_args

sys.dont_write_bytecode = True

SAFE_FIELDS = frozenset({
    "tools", "inputSchema", "input_schema", "outputSchema", "output_schema",
    "annotations", "name", "description", "title", "parameters", "icons",
    "src", "mimeType", "mime_type", "sizes", "theme", "execution",
    "taskSupport", "task_support", "meta", "_meta", "type", "properties",
    "required", "additionalProperties", "oneOf", "anyOf", "allOf", "items",
    "enum", "$ref", "$defs", "cacheScope", "cache_scope", "ttlMs", "ttl_ms",
    "resultType", "result_type", "supportedVersions", "supported_versions",
    "capabilities", "serverInfo", "server_info", "protocolVersion",
    "protocol_version", "instructions", "nextCursor", "next_cursor",
    "resources", "prompts", "logging", "experimental", "sampling",
    "elicitation", "listChanged", "list_changed", "url", "version",
})
SAFE_MODELS = frozenset({
    "ListToolsResult", "InitializeResult", "DiscoverResult", "ProxyTool",
    "Tool", "InputSchema", "OutputSchema", "JSONRPCMessage", "ToolAnnotations",
    "Implementation", "ServerCapabilities", "Icon", "ToolExecution",
})
SAFE_EXCEPTIONS = frozenset({
    "ValidationError", "RuntimeError", "ValueError", "ToolError", "MCPError",
    "TimeoutError", "HTTPStatusError", "ConnectError", "ReadTimeout",
    "ExceptionGroup", "BaseExceptionGroup", "FileNotFoundError", "ImportError",
    "ModuleNotFoundError", "PermissionError",
})
SAFE_VERSIONS = frozenset({
    "2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25", "2026-07-28",
})


def diagnostic_rows(exc):
    """Keep only known model names, fixed field paths and built-in error codes."""
    from pydantic import ValidationError
    from pydantic_core import ErrorType

    safe_error_types = frozenset(get_args(ErrorType))
    pending = [exc]
    seen = set()
    rows = []
    while pending and len(seen) < 16:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        category = type(current).__name__
        category = category if category in SAFE_EXCEPTIONS else "<exception>"
        rows.append({"exception": category})
        status = getattr(getattr(current, "response", None), "status_code", None)
        if isinstance(status, int) and 100 <= status <= 599:
            rows.append({"http_status": status})
        if isinstance(current, ValidationError):
            model = current.title if current.title in SAFE_MODELS else "<model>"
            issues = current.errors(
                include_url=False, include_context=False, include_input=False,
            )
            rows.append({"model": model, "error_count": len(issues)})
            for issue in issues[:12]:
                loc = [
                    part if isinstance(part, int) or part in SAFE_FIELDS else "<field>"
                    for part in issue.get("loc", ())
                ]
                kind = issue.get("type")
                rows.append({
                    "loc": loc,
                    "type": kind if kind in safe_error_types else "<type>",
                })
        pending.extend(getattr(current, "exceptions", ()))
        if current.__cause__ is not None:
            pending.append(current.__cause__)
        if current.__context__ is not None:
            pending.append(current.__context__)
    return rows


def report_error(label, exc):
    for row in diagnostic_rows(exc):
        print(label, json.dumps(row, ensure_ascii=True), flush=True)


async def inspect(label, target, mode, known_names):
    from fastmcp import Client

    print(label, "checking...", flush=True)
    try:
        async with asyncio.timeout(30):
            async with Client(target, mode=mode) as client:
                tools = await client.list_tools()
                names = sorted(tool.name for tool in tools if tool.name in known_names)
                protocol = client.protocol_version
                print(label, json.dumps({
                    "status": "ok", "tool_count": len(tools), "known_tools": names,
                    "protocol": protocol if protocol in SAFE_VERSIONS else "<version>",
                }), flush=True)
        return True
    except Exception as exc:
        report_error(label, exc)
        return False


async def main(gateway_dir):
    sys.path.insert(0, str(gateway_dir.resolve(strict=True)))
    import gateway_server as gateway
    from dotenv import dotenv_values

    values = dotenv_values(gateway.ENV_FILE, interpolate=False)
    pat = values.get("GITEE_ACCESS_TOKEN")
    if not isinstance(pat, str) or not pat.strip():
        print("CONFIG: GITEE_ACCESS_TOKEN is missing or empty", flush=True)
        return 1

    known_upstream = set(gateway.READ_TOOLS)
    known_gateway = {"whoami", "create_private_project"} | {
        "gitee_" + name for name in known_upstream
    }
    for label, mode in (
        ("UPSTREAM_LEGACY", "legacy"),
        ("UPSTREAM_AUTO", "auto"),
        ("UPSTREAM_MODERN", "2026-07-28"),
    ):
        await inspect(label, gateway.make_transport(pat, False), mode, known_upstream)

    # A temporary in-process instance; the running HTTP service is not changed.
    await inspect("GATEWAY_MODERN", gateway.build_server(), "2026-07-28", known_gateway)
    print("DIAGNOSTICS COMPLETE", flush=True)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway-dir", type=Path,
                        default=Path("/opt/gitee-mcp-gateway/gateway"))
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    try:
        raise SystemExit(asyncio.run(main(args.gateway_dir)))
    except Exception as exc:
        report_error("DIAG", exc)
        raise SystemExit(1) from None
