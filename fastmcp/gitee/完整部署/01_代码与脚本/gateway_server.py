"""Single-user OAuth gateway for Gitee repositories, PRs, issues and hooks."""
import logging
import secrets
import stat
import sys
from importlib.metadata import version
from pathlib import Path

from fastmcp import FastMCP, Client
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.server import create_proxy
from fastmcp.server.transforms.visibility import Visibility
from fastmcp.server.transforms import Transform
from mcp_types import ToolAnnotations
from fastmcp.server.middleware import Middleware
from fastmcp.tools.base import ToolResult
from fastmcp.exceptions import ToolError
import httpx2
import json
from jsonschema import validate
from fastmcp.server.auth.providers.github import GitHubProvider
from fastmcp.server.dependencies import get_access_token
from auth_policy import allowed_identity, identity_result
from gitee_repository_tools import register_repository_tools

BASE_URL = "https://mcp.example.com"  # Placeholder: match ngrok, allowed_hosts and the OAuth App.
ENV_FILE = Path("/opt/gitee-mcp-gateway/gateway/.env")


class SingleUserGitHubProvider(GitHubProvider):
    async def load_access_token(self, token):
        # The superclass validates its own signed JWT, looks up the upstream
        # OAuth token, and verifies that token with GitHub before returning claims.
        try:
            verified = await super().load_access_token(token)
        except Exception:
            return None
        return verified if allowed_identity(verified) else None


def whoami() -> dict[str, str]:
    """Return the permitted, authenticated GitHub login and test status."""
    # Defense in depth, in addition to provider-wide authentication enforcement.
    return identity_result(get_access_token())


class SafeUpstreamErrors(Middleware):
    async def on_call_tool(self, context, call_next):
        name = getattr(context.message, "name", "").removeprefix("gitee_")
        message = (
            "Gitee write outcome is unconfirmed; check the target before retrying."
            if name in UPSTREAM_WRITE_TOOLS else
            "Upstream operation failed; check service configuration."
        )
        try:
            result = await call_next(context)
        except Exception:
            return ToolResult(content=message, is_error=True)
        if result.is_error:
            return ToolResult(content=message, is_error=True)
        return result


UPSTREAM_READ_TOOLS = {
    "get_user_info", "search_users", "list_user_notifications",
    "list_user_repos", "get_file_content", "list_releases",
    "search_open_source_repositories", "search_files_by_content",
    "compare_branches_tags", "list_repo_pulls", "get_pull_detail",
    "get_diff_files", "list_comments", "get_repo_issue_detail", "list_repo_issues",
}
UPSTREAM_WRITE_TOOLS = {
    "create_repo", "fork_repository", "create_release", "merge_pull",
    "create_pull", "update_pull", "manage_pull_review", "create_comment",
    "create_issue", "update_issue",
}
# Retain this exported name for older offline checks and the diagnostic script.
READ_TOOLS = UPSTREAM_READ_TOOLS
UPSTREAM = "https://api.gitee.com/mcp"


class ToolOperationAnnotations(Transform):
    """Preserve proxy routing/schema while describing each operation correctly."""

    def annotate(self, tool):
        read_only = tool.name in UPSTREAM_READ_TOOLS
        destructive = tool.name in {"merge_pull", "update_pull", "manage_pull_review", "update_issue"}
        return tool.model_copy(update={"annotations": ToolAnnotations(
            readOnlyHint=read_only, destructiveHint=destructive,
            idempotentHint=read_only, openWorldHint=True,
        )})

    async def list_tools(self, tools):
        return [self.annotate(tool) for tool in tools]

    async def get_tool(self, name, call_next, *, version=None):
        tool = await call_next(name, version=version)
        return self.annotate(tool) if tool is not None else None


class CompleteToolCatalog(Middleware):
    """Reject partial discovery results instead of advertising only whoami."""

    def __init__(self, expected_names):
        self.expected_names = frozenset(expected_names)

    async def on_list_tools(self, context, call_next):
        try:
            tools = await call_next(context)
            if (len(tools) != len(self.expected_names)
                or {tool.name for tool in tools} != self.expected_names):
                actual = {tool.name for tool in tools}
                # Missing names come only from our static local allowlist.
                # Do not log names or payloads supplied unexpectedly upstream.
                print(
                    "TOOL CATALOG MISMATCH: missing="
                    + ",".join(sorted(self.expected_names - actual))
                    + f"; unexpected_count={len(actual - self.expected_names)}"
                    + f"; duplicate_count={len(tools) - len(actual)}",
                    file=sys.stderr, flush=True,
                )
                raise RuntimeError("Incomplete tool catalog")
        except Exception as exc:
            # Only the exception category is logged, never its payload or headers.
            print(
                f"TOOL DISCOVERY FAILED ({type(exc).__name__}); "
                "check Gitee upstream access and the configured tool allowlist",
                file=sys.stderr, flush=True,
            )
            raise ToolError(
                "Gitee tool discovery failed; check the gateway configuration "
                "and upstream access, then refresh the plugin."
            ) from None
        return tools


def unpack_result(result):
    if result.is_error:
        raise RuntimeError("Upstream tool failed")
    payload = result.structured_content or result.data
    if isinstance(payload, dict):
        return payload
    for content in result.content:
        if getattr(content, "type", None) == "text":
            return json.loads(content.text)
    return None


def private_arguments(tool):
    schema = tool.input_schema
    props = schema.get("properties", {})
    if props.get("private", {}).get("type") != "boolean":
        raise RuntimeError("Upstream private support is unverified; use the manual private-repository step")
    if "user" not in props.get("owner_type", {}).get("enum", []):
        raise RuntimeError("Upstream personal ownership support is unverified")
    if not {"name", "path", "auto_init"}.issubset(props):
        raise RuntimeError("Upstream schema changed; do not create")
    args = {"owner_type": "user", "name": "a-share-investment-engine",
            "path": "a-share-investment-engine", "private": True, "auto_init": False}
    validate(instance=args, schema=schema)
    return args


def make_transport(pat, write_mode):
    allow = UPSTREAM_READ_TOOLS | (UPSTREAM_WRITE_TOOLS if write_mode else set())
    own_headers = {"Authorization": "Bearer " + pat,
                   "X-MCP-Enabled-Tools": ",".join(sorted(allow))}
    def isolated_http_client(**kwargs):
        # Drop ALL ambient headers/auth: FastMCP otherwise inherits front-end headers.
        return httpx2.AsyncClient(headers=own_headers, auth=None,
                                  follow_redirects=False, trust_env=False,
                                  timeout=kwargs.get("timeout", 30.0))
    return StreamableHttpTransport(UPSTREAM, headers=own_headers,
                                   httpx_client_factory=isolated_http_client)


def build_server():
    if version("fastmcp") != "4.0.11" or version("fastmcp-slim") != "4.0.11":
        raise RuntimeError("This experiment requires FastMCP and fastmcp-slim 4.0.11")
    if version("mcp") != "2.3.0":
        raise RuntimeError("This experiment requires MCP 2.3.0")
    info = ENV_FILE.lstat()
    if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o077:
        raise RuntimeError("The configured .env must be a regular private file (chmod 600)")
    from dotenv import dotenv_values
    from key_value.aio.stores.memory import MemoryStore
    values = dotenv_values(ENV_FILE, interpolate=False)
    client_id = values.get("GITHUB_CLIENT_ID")
    client_secret = values.get("GITHUB_CLIENT_SECRET")
    if not client_id or not client_secret or not client_id.strip() or not client_secret.strip():
        raise RuntimeError("Set both GitHub OAuth app fields in the configured .env")
    pat = values.get("GITEE_ACCESS_TOKEN")
    mode = values.get("GITEE_MODE", "READ")
    if not isinstance(pat, str) or not pat.strip() or mode not in {"READ", "WRITE"}:
        raise RuntimeError("Configure GITEE_ACCESS_TOKEN and READ or WRITE mode")
    transport = make_transport(pat, mode == "WRITE")
    auth = SingleUserGitHubProvider(
        client_id=client_id,
        client_secret=client_secret,
        base_url=BASE_URL,
        issuer_url=BASE_URL,
        redirect_path="/auth/callback",
        required_scopes=["read:user"],
        require_authorization_consent=True,
        # Generated once at startup, never per request. State is memory-only.
        jwt_signing_key=secrets.token_bytes(32),
        client_storage=MemoryStore(max_entries_per_collection=1000),
    )
    mcp = FastMCP("G8 Gitee Gateway", auth=auth, mask_error_details=True)
    # A failed provider must not silently disappear from tools/list.
    mcp.provider_error_strategy = "raise"
    mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False,
                          "idempotentHint": True, "openWorldHint": False})(whoami)
    # Gitee currently negotiates 2025-03-26. Mirroring a modern frontend would
    # validate its legacy tools/list response against the wrong wire schema.
    upstream = create_proxy(transport, name="Gitee scoped bridge",
                            mask_error_details=True, provider_error_strategy="raise",
                            mode="legacy")
    upstream.add_middleware(SafeUpstreamErrors())
    upstream.add_transform(Visibility(False, match_all=True))
    allow = UPSTREAM_READ_TOOLS | (UPSTREAM_WRITE_TOOLS if mode == "WRITE" else set())
    upstream.add_transform(Visibility(True, names=allow, components={"tool"}))
    upstream.add_transform(ToolOperationAnnotations())
    mcp.mount(upstream, namespace="gitee")

    local_names = register_repository_tools(
        mcp, pat, mode == "WRITE", lambda: identity_result(get_access_token()),
    )

    if mode == "WRITE":
        @mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False,
                              "idempotentHint": False, "openWorldHint": True})
        async def create_private_project(confirm: bool = False) -> dict:
            """Create only the personal private a-share-investment-engine repository after explicit confirmation."""
            identity_result(get_access_token())
            if confirm is not True:
                raise PermissionError("Explicit confirm=true is required")
            try:
                async with Client(make_transport(pat, True), mode="legacy") as backend:
                    tools = await backend.list_tools()
                    tool = next((t for t in tools if t.name == "create_repo"), None)
                    if tool is None:
                        raise RuntimeError("create_repo not available")
                    args = private_arguments(tool)
                    identity = await backend.call_tool("get_user_info", {})
                    user = unpack_result(identity)
                    if not isinstance(user, dict) or not isinstance(user.get("id"), int):
                        raise RuntimeError("Gitee owner not verified")
                    result = await backend.call_tool("create_repo", args)
                    if result.is_error:
                        raise RuntimeError("Creation returned an error")
                    payload = unpack_result(result)
                    if (not isinstance(payload, dict) or payload.get("private") is not True
                        or payload.get("path") != "a-share-investment-engine"
                        or not isinstance(payload.get("owner"), dict)
                        or payload["owner"].get("id") != user["id"]):
                        raise RuntimeError("Private repository result not verified")
                    return {"status": "created_private", "private": True,
                            "html_url": payload.get("html_url"), "path": payload.get("path")}
            except Exception:
                raise ToolError("Creation not verified. Do not retry; check the Gitee repository page first.") from None

    expected_names = {"whoami"} | {f"gitee_{name}" for name in allow} | local_names
    if mode == "WRITE":
        expected_names.add("create_private_project")
    mcp.add_middleware(CompleteToolCatalog(expected_names))
    return mcp


def main():
    # The experiment deliberately suppresses library logs, including OAuth URLs.
    # Discovery failures are reported separately using sanitized exception types.
    logging.disable(logging.CRITICAL)
    try:
        mcp = build_server()
        print("Gitee gateway starting on 127.0.0.1:8765; Ctrl+C to stop", flush=True)
        mcp.run(transport="http", host="127.0.0.1", port=8765,
                log_level="critical", uvicorn_config={"access_log": False},
                host_origin_protection=True,
                allowed_hosts=["mcp.example.com"],
                allowed_origins=[BASE_URL])
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        # Do not print exception payloads, credentials, requests, or tracebacks.
        print(f"STARTUP FAILED ({type(exc).__name__}); check versions, .env permissions and port", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
