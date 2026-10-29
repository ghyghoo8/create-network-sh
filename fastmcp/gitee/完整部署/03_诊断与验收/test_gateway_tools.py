"""Offline checks for the expanded G8 gateway; never contacts or mutates Gitee.

Run beside gateway_server.py and gitee_repository_tools.py with the gateway venv:
    python test_gateway_tools.py

The OAuth provider is replaced only inside these fixtures. Production policy files
and live credentials are neither required nor modified.
"""

import base64
import contextlib
import importlib.util
import io
import json
import logging
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import httpx2
from fastmcp import Client, FastMCP


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
PAT = "offline-only-private-credential-DO-NOT-LEAK"
FRONT_TOKEN = "offline-only-frontend-token-DO-NOT-FORWARD"
ORIGINAL_CLIENT = httpx2.AsyncClient
READ = {
    "list_user_repos", "get_file_content", "list_releases",
    "search_open_source_repositories", "search_files_by_content",
    "compare_branches_tags", "list_repo_pulls", "get_pull_detail",
    "get_diff_files", "list_comments", "get_repo_issue_detail",
    "list_repo_issues", "get_user_info", "search_users",
    "list_user_notifications",
}
WRITE = {
    "create_repo", "fork_repository", "create_release", "merge_pull",
    "create_pull", "update_pull", "manage_pull_review", "create_comment",
    "create_issue", "update_issue",
}


def load_gateway():
    fixture_policy = types.ModuleType("auth_policy")
    fixture_policy.allowed_identity = lambda token: True
    fixture_policy.identity_result = lambda token: {
        "status": "ok", "github_login": "offline-fixture",
    }
    spec = importlib.util.spec_from_file_location(
        "gateway_under_offline_test", ROOT / "gateway_server.py"
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"auth_policy": fixture_policy}):
        spec.loader.exec_module(module)
    return module


gateway = load_gateway()
import gitee_repository_tools as repository_tools


class MockAPI:
    def __init__(self, handler):
        self.handler = handler
        self.requests = []

    def handle(self, request):
        self.requests.append(request)
        assert request.headers.get("Authorization") == "Bearer " + PAT
        assert PAT not in str(request.url), "Token must never appear in a URL"
        return self.handler(request)

    def factory(self, **kwargs):
        return ORIGINAL_CLIENT(transport=httpx2.MockTransport(self.handle), **kwargs)


class LegacyMCP(MockAPI):
    def __init__(self, omitted=None, duplicate=False):
        self.omitted = omitted
        self.duplicate = duplicate
        self.protocol_records = []
        super().__init__(self.respond)

    def respond(self, request):
        if request.method != "POST":
            return httpx2.Response(405)
        body = json.loads(request.content)
        method = body.get("method")
        self.protocol_records.append((method, request.headers.get("mcp-protocol-version")))
        if "id" not in body:
            return httpx2.Response(202)
        envelope = {"jsonrpc": "2.0", "id": body["id"]}
        if method == "server/discover":
            envelope["error"] = {"code": -32601, "message": "Method not found"}
        elif method == "initialize":
            envelope["result"] = {
                "protocolVersion": "2025-03-26", "capabilities": {"tools": {}},
                "serverInfo": {"name": "offline-Gitee", "version": "1"},
            }
        elif method == "tools/list":
            enabled = set(request.headers["X-MCP-Enabled-Tools"].split(","))
            schemas = []
            for name in sorted(enabled - {self.omitted}):
                parameters = {"type": "object", "properties": {}}
                if name == "get_file_content":
                    parameters = {
                        "type": "object",
                        "properties": {key: {"type": "string"}
                                       for key in ("owner", "repo", "path")},
                        "required": ["owner", "repo", "path"],
                    }
                schemas.append({
                    "name": name, "description": "Offline fixture",
                    "inputSchema": parameters,
                    # Deliberately wrong hints: gateway must classify them itself.
                    "annotations": {"readOnlyHint": name in WRITE,
                                    "destructiveHint": name in READ},
                })
            if self.duplicate and schemas:
                schemas.append(schemas[0])
            # Old-protocol wire response intentionally lacks modern cache fields.
            envelope["result"] = {"tools": schemas}
        elif method == "tools/call":
            params = body.get("params", {})
            data = {"tool": params.get("name"),
                    "arguments": params.get("arguments", {}), "content": "fixture"}
            envelope["result"] = {
                "content": [{"type": "text", "text": json.dumps(data)}],
                "structuredContent": data,
            }
        else:
            envelope["result"] = {}
        return httpx2.Response(200, json=envelope)


@contextlib.contextmanager
def configured_gateway(write_mode, api):
    with tempfile.TemporaryDirectory(prefix="g8-tools-offline-") as folder:
        env_file = Path(folder) / ".env"
        env_file.write_text(
            "GITHUB_CLIENT_ID=fixture-id\nGITHUB_CLIENT_SECRET=fixture-secret\n"
            f"GITEE_ACCESS_TOKEN={PAT}\nGITEE_MODE={'WRITE' if write_mode else 'READ'}\n",
            encoding="utf-8",
        )
        env_file.chmod(0o600)
        package_versions = {"fastmcp": "4.0.11", "fastmcp-slim": "4.0.11", "mcp": "2.3.0"}
        with patch.object(gateway, "ENV_FILE", env_file), \
             patch.object(gateway, "version", package_versions.__getitem__), \
             patch.object(gateway, "SingleUserGitHubProvider", lambda **kwargs: None), \
             patch.object(gateway, "get_access_token", lambda: None), \
             patch.object(httpx2, "AsyncClient", api.factory):
            yield gateway.build_server()


class GatewayTests(unittest.IsolatedAsyncioTestCase):
    def test_official_allowlist_and_credential_isolation(self):
        self.assertEqual(gateway.UPSTREAM_READ_TOOLS, READ)
        self.assertEqual(gateway.UPSTREAM_WRITE_TOOLS, WRITE)
        for write_mode in (False, True):
            transport = gateway.make_transport(PAT, write_mode)
            client = transport.httpx_client_factory(
                headers={"Authorization": "Bearer " + FRONT_TOKEN,
                         "X-MCP-Enabled-Tools": "delete_everything",
                         "X-Extra": FRONT_TOKEN}, auth=FRONT_TOKEN,
            )
            self.assertEqual(client.headers["Authorization"], "Bearer " + PAT)
            self.assertNotIn(FRONT_TOKEN, str(client.headers))
            self.assertIsNone(client.auth)
            allowed = set(client.headers["X-MCP-Enabled-Tools"].split(","))
            self.assertEqual(allowed, READ | (WRITE if write_mode else set()))

    async def test_catalog_and_legacy_backend_for_all_frontend_modes(self):
        for write_mode in (False, True):
            for frontend in ("legacy", "auto", "2026-07-28"):
                with self.subTest(write_mode=write_mode, frontend=frontend):
                    api = LegacyMCP()
                    with configured_gateway(write_mode, api) as server:
                        async with Client(server, mode=frontend) as client:
                            tools = await client.list_tools()
                            local_names = repository_tools.LOCAL_READ_TOOLS | (
                                repository_tools.LOCAL_WRITE_TOOLS if write_mode else set()
                            )
                            expected = {"whoami"} | local_names | {
                                "gitee_" + name for name in READ | (WRITE if write_mode else set())
                            }
                            if write_mode:
                                expected.add("create_private_project")
                            self.assertEqual({tool.name for tool in tools}, expected)
                            self.assertEqual(len(tools), len(expected))
                            by_name = {tool.name: tool for tool in tools}
                            for name in READ:
                                self.assertTrue(by_name["gitee_" + name].annotations.read_only_hint)
                                self.assertFalse(by_name["gitee_" + name].annotations.destructive_hint)
                            for name in WRITE if write_mode else ():
                                self.assertFalse(by_name["gitee_" + name].annotations.read_only_hint)
                            for name in repository_tools.LOCAL_READ_TOOLS:
                                self.assertTrue(by_name[name].annotations.read_only_hint)
                                self.assertFalse(by_name[name].annotations.destructive_hint)
                            for name in repository_tools.LOCAL_WRITE_TOOLS if write_mode else ():
                                self.assertFalse(by_name[name].annotations.read_only_hint)
                            if write_mode:
                                self.assertTrue(by_name["gitee_test_hook"].annotations.destructive_hint)
                            result = await client.call_tool("gitee_get_file_content", {
                                "owner": "fixture", "repo": "project", "path": "README.md",
                            })
                            self.assertEqual(result.data["content"], "fixture")
                            if write_mode:
                                result = await client.call_tool("gitee_create_issue", {})
                                self.assertEqual(result.data["tool"], "create_issue")
                            else:
                                result = await client.call_tool("gitee_create_issue", {}, raise_on_error=False)
                                self.assertTrue(result.is_error)
                    versions = [version for method, version in api.protocol_records
                                if method in {"tools/list", "tools/call"}]
                    self.assertTrue(versions)
                    self.assertEqual(set(versions), {"2025-03-26"})

    async def test_incomplete_catalog_is_rejected(self):
        api = LegacyMCP(omitted="get_file_content")
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), configured_gateway(True, api) as server:
            async with Client(server, mode="2026-07-28") as client:
                with self.assertRaises(Exception) as caught:
                    await client.list_tools()
        self.assertNotIn(PAT, str(caught.exception) + stderr.getvalue())
        self.assertTrue(stderr.getvalue().strip())

    async def test_duplicate_catalog_names_are_rejected(self):
        catalog = gateway.CompleteToolCatalog({"one", "two"})
        async def duplicated(context):
            return [types.SimpleNamespace(name=name) for name in ("one", "two", "two")]
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(Exception):
                await catalog.on_list_tools(None, duplicated)


class RepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def invoke(self, name, arguments, handler=None, write_mode=True):
        api = MockAPI(handler or (lambda request: httpx2.Response(200, json={"ok": True})))
        identities = []
        server = FastMCP("offline-repository-tests", mask_error_details=True)
        def identity_check():
            identities.append("checked")
            return {"github_login": "offline-fixture"}
        registered = repository_tools.register_repository_tools(server, PAT, write_mode, identity_check)
        self.assertEqual(registered, repository_tools.LOCAL_READ_TOOLS | (
            repository_tools.LOCAL_WRITE_TOOLS if write_mode else set()
        ))
        with patch.object(httpx2, "AsyncClient", api.factory):
            async with Client(server, mode="legacy") as client:
                result = await client.call_tool(name, arguments, raise_on_error=False)
        return result, api.requests, identities

    async def test_read_mode_does_not_register_write_tools(self):
        result, requests, identities = await self.invoke(
            "gitee_create_file", {"owner": "fixture", "repo": "demo", "path": "README.md",
                                  "message": "offline", "content": "text"}, write_mode=False,
        )
        self.assertTrue(result.is_error)
        self.assertEqual(requests, [])

    async def test_utf8_create_file_encodes_content_and_path(self):
        text = "中文内容\n"
        result, requests, identities = await self.invoke("gitee_create_file", {
            "owner": "fixture", "repo": "demo", "path": "资讯与催化/契约 #1.json",
            "message": "Add contract", "content": text, "branch": "main",
        })
        self.assertFalse(result.is_error)
        self.assertEqual(identities, ["checked"])
        self.assertEqual(len(requests), 1)
        request = requests[0]
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.url.path, "/api/v5/repos/fixture/demo/contents/资讯与催化/契约 #1.json")
        self.assertIn(b"%23", request.url.raw_path)
        self.assertNotIn(b"#", request.url.raw_path)
        payload = json.loads(request.content)
        self.assertEqual(base64.b64decode(payload["content"]), text.encode())
        self.assertEqual(payload["branch"], "main")
        self.assertEqual(payload["message"], "Add contract")

    async def test_base64_binary_round_trip(self):
        binary = b"PK\x03\x04\x00\xff\x80DOCX-fixture\x00"
        encoded = base64.b64encode(binary).decode()
        result, requests, identities = await self.invoke("gitee_create_file", {
            "owner": "fixture", "repo": "demo", "path": "计划.docx",
            "message": "Add document", "content": encoded, "encoding": "base64",
        })
        self.assertFalse(result.is_error)
        self.assertEqual(base64.b64decode(json.loads(requests[0].content)["content"]), binary)
        self.assertEqual(identities, ["checked"])

    async def test_invalid_base64_is_rejected_before_network(self):
        result, requests, identities = await self.invoke("gitee_create_file", {
            "owner": "fixture", "repo": "demo", "path": "plan.docx", "message": "Add document",
            "content": "not!base64", "encoding": "base64",
        })
        self.assertTrue(result.is_error)
        self.assertEqual(requests, [])

    async def test_update_and_delete_require_sha(self):
        for name in ("gitee_update_file", "gitee_delete_file"):
            args = {"owner": "fixture", "repo": "demo", "path": "README.md", "message": "Change file"}
            if name == "gitee_update_file":
                args["content"] = "New text"
            result, requests, _ = await self.invoke(name, args)
            self.assertTrue(result.is_error)
            self.assertEqual(requests, [])
            args["sha"] = "a" * 40
            result, requests, identities = await self.invoke(name, args)
            self.assertFalse(result.is_error)
            self.assertEqual(requests[0].method, "PUT" if name == "gitee_update_file" else "DELETE")
            self.assertEqual(json.loads(requests[0].content)["sha"], "a" * 40)
            self.assertEqual(identities, ["checked"])

    async def test_traversal_and_cross_host_inputs_are_rejected(self):
        valid = {"owner": "fixture", "repo": "demo", "path": "README.md",
                 "message": "Add file", "content": "safe"}
        for bad in ({"owner": "../other"}, {"repo": "../../user"},
                    {"path": "../.env"}, {"path": "/absolute/file"},
                    {"path": "https://evil.invalid/file"},
                    {"path": "%252e%252e/.env"}, {"owner": "%2Fother"},
                    {"path": "nested/../.env"}, {"path": "nested//file"}):
            with self.subTest(bad=bad):
                result, requests, _ = await self.invoke("gitee_create_file", {**valid, **bad})
                self.assertTrue(result.is_error)
                self.assertEqual(requests, [])

    async def test_failed_write_is_not_retried_or_leaked(self):
        for status in (302, 307, 401, 403, 409, 422, 500, 502):
            with self.subTest(status=status):
                handler = lambda request: httpx2.Response(status, json={"message": PAT, "url": FRONT_TOKEN})
                result, requests, identities = await self.invoke("gitee_create_file", {
                    "owner": "fixture", "repo": "demo", "path": "README.md",
                    "message": "Add file", "content": "safe",
                }, handler=handler)
                self.assertTrue(result.is_error)
                self.assertEqual(len(requests), 1)
                serialized = repr(result)
                self.assertNotIn(PAT, serialized)
                self.assertNotIn(FRONT_TOKEN, serialized)
                self.assertEqual(identities, ["checked"])

    async def test_denied_identity_prevents_api_call(self):
        server = FastMCP("offline-denied-tests", mask_error_details=True)
        api = MockAPI(lambda request: httpx2.Response(200, json={"ok": True}))
        def reject():
            raise PermissionError("Denied fixture")
        repository_tools.register_repository_tools(server, PAT, True, reject)
        with patch.object(httpx2, "AsyncClient", api.factory):
            async with Client(server, mode="legacy") as client:
                result = await client.call_tool("gitee_create_file", {
                    "owner": "fixture", "repo": "demo", "path": "README.md",
                    "message": "Add file", "content": "safe",
                }, raise_on_error=False)
        self.assertTrue(result.is_error)
        self.assertEqual(api.requests, [])

    async def test_repository_metadata_settings_and_pagination(self):
        base = {"owner": "fixture", "repo": "demo"}
        for name, suffix in (("gitee_get_repository", ""),
                             ("gitee_list_branches", "/branches"),
                             ("gitee_list_tags", "/tags")):
            args = dict(base)
            if suffix:
                args.update(page=2, per_page=50, sort="updated", direction="desc")
            result, requests, identities = await self.invoke(name, args)
            self.assertFalse(result.is_error)
            self.assertEqual(requests[0].method, "GET")
            self.assertEqual(requests[0].url.path, "/api/v5/repos/fixture/demo" + suffix)
            if suffix:
                self.assertEqual(dict(requests[0].url.params), {
                    "page": "2", "per_page": "50", "sort": "updated", "direction": "desc",
                })
            self.assertEqual(identities, ["checked"])
        result, requests, identities = await self.invoke("gitee_update_repository", {
            **base, "name": "Keep current name", "private": False, "has_issues": False,
            "has_wiki": True, "online_edit_enabled": False,
        })
        self.assertFalse(result.is_error)
        self.assertEqual(requests[0].method, "PATCH")
        payload = json.loads(requests[0].content)
        self.assertIs(payload["private"], False)
        self.assertIs(payload["has_issues"], False)
        self.assertIs(payload["has_wiki"], True)
        self.assertIs(payload["online_edit_enabled"], False)
        self.assertNotIn("default_branch", payload)
        self.assertEqual(identities, ["checked"])

    async def test_branch_tag_and_tree_keep_reference_semantics(self):
        base = {"owner": "fixture", "repo": "demo"}
        for name, suffix, args in (
            ("gitee_create_branch", "/branches", {"branch_name": "feature/review", "refs": "main"}),
            ("gitee_create_tag", "/tags", {"tag_name": "v1.0", "refs": "feature/review", "tag_message": "Release"}),
        ):
            result, requests, identities = await self.invoke(name, {**base, **args})
            self.assertFalse(result.is_error)
            self.assertEqual(requests[0].method, "POST")
            self.assertEqual(requests[0].url.path, "/api/v5/repos/fixture/demo" + suffix)
            self.assertEqual(json.loads(requests[0].content), args)
            self.assertEqual(identities, ["checked"])
        result, requests, identities = await self.invoke("gitee_list_tree", {
            **base, "sha": "feature/review", "recursive": True,
        })
        self.assertFalse(result.is_error)
        self.assertEqual(requests[0].method, "GET")
        self.assertIn(b"/git/trees/feature%2Freview", requests[0].url.raw_path)
        self.assertEqual(dict(requests[0].url.params), {"recursive": "1"})
        self.assertEqual(identities, ["checked"])

    async def test_multi_file_commit_is_one_request_and_preserves_bytes(self):
        binary = b"PK\x03\x04\x00\xff\x80DOCX-multi-file\x00"
        encoded = base64.b64encode(binary).decode()
        actions = [
            {"action": "create", "path": "说明.md", "content": "中文\n", "encoding": "text"},
            {"action": "create", "path": "方案.docx", "content": encoded, "encoding": "base64"},
            {"action": "update", "path": "README.md", "content": "Changed", "last_commit_id": "b" * 40},
        ]
        result, requests, identities = await self.invoke("gitee_commit_files", {
            "owner": "fixture", "repo": "demo", "branch": "review/import", "start_branch": "main",
            "message": "Import project files", "actions": actions,
            "author": {"name": "Fixture", "email": "fixture@example.invalid"},
        })
        self.assertFalse(result.is_error)
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].method, "POST")
        self.assertEqual(requests[0].url.path, "/api/v5/repos/fixture/demo/commits")
        payload = json.loads(requests[0].content)
        self.assertEqual(payload["branch"], "review/import")
        self.assertEqual(payload["start_branch"], "main")
        self.assertEqual(payload["actions"][0]["content"], "中文\n")
        self.assertEqual(base64.b64decode(payload["actions"][1]["content"]), binary)
        self.assertEqual(payload["actions"][2]["last_commit_id"], "b" * 40)
        self.assertEqual(identities, ["checked"])

    async def test_invalid_multi_file_actions_do_not_send_partial_commit(self):
        base = {"owner": "fixture", "repo": "demo", "branch": "main", "message": "Import"}
        invalid_actions = [
            [],
            [{"action": "create", "path": "valid.md", "content": "valid"},
             {"action": "create", "path": "../.env", "content": "unsafe"}],
            [{"action": "create", "path": "file.docx", "content": "not!base64", "encoding": "base64"}],
            [{"action": "move", "path": "target.md"}],
            [{"action": "update", "path": "file.md", "content": "valid", "last_commit_id": "short"}],
        ]
        for actions in invalid_actions:
            with self.subTest(actions=actions):
                result, requests, identities = await self.invoke("gitee_commit_files", {**base, "actions": actions})
                self.assertTrue(result.is_error)
                self.assertEqual(requests, [])

    async def test_hook_boolean_false_and_secret_redaction(self):
        hook_secret = "hook-password-that-must-not-be-returned"
        response = {
            "id": 7, "password": hook_secret,
            "url": "https://username:private@hook.example.invalid/events?token=secret#private",
            "nested": {"signing_secret": hook_secret, "authorization": PAT},
            "push_events": False,
        }
        result, requests, identities = await self.invoke("gitee_create_hook", {
            "owner": "fixture", "repo": "demo", "url": "https://hook.example.invalid/events",
            "password": hook_secret, "encryption_type": 0, "push_events": False,
            "issues_events": False, "tag_push_events": False,
        }, handler=lambda request: httpx2.Response(201, json=response))
        self.assertFalse(result.is_error)
        self.assertEqual(requests[0].method, "POST")
        payload = json.loads(requests[0].content)
        self.assertEqual(payload["password"], hook_secret)
        self.assertEqual(payload["encryption_type"], 0)
        self.assertIs(payload["push_events"], False)
        self.assertIs(payload["issues_events"], False)
        self.assertEqual(result.data["url"], "https://hook.example.invalid/events")
        self.assertEqual(result.data["password"], "[REDACTED]")
        self.assertNotIn(hook_secret, repr(result))
        self.assertNotIn(PAT, repr(result))
        self.assertEqual(identities, ["checked"])
        result, requests, identities = await self.invoke("gitee_update_hook", {
            "owner": "fixture", "repo": "demo", "hook_id": 7,
            "url": "https://hook.example.invalid/events", "push_events": False,
        })
        self.assertFalse(result.is_error)
        self.assertEqual(requests[0].method, "PATCH")
        payload = json.loads(requests[0].content)
        self.assertIs(payload["push_events"], False)
        self.assertNotIn("issues_events", payload)
        self.assertNotIn("password", payload)

    async def test_hook_get_list_delete_and_test_methods(self):
        base = {"owner": "fixture", "repo": "demo"}
        for name, args, method, suffix in (
            ("gitee_list_hooks", base, "GET", "/hooks"),
            ("gitee_get_hook", {**base, "hook_id": 7}, "GET", "/hooks/7"),
            ("gitee_delete_hook", {**base, "hook_id": 7}, "DELETE", "/hooks/7"),
            ("gitee_test_hook", {**base, "hook_id": 7}, "POST", "/hooks/7/tests"),
        ):
            with self.subTest(name=name):
                result, requests, identities = await self.invoke(name, args)
                self.assertFalse(result.is_error)
                self.assertEqual(requests[0].method, method)
                self.assertEqual(requests[0].url.path, "/api/v5/repos/fixture/demo" + suffix)
                self.assertEqual(identities, ["checked"])

    async def test_timeout_does_not_retry_or_expose_exception_text(self):
        def timeout(request):
            raise httpx2.ReadTimeout(PAT + FRONT_TOKEN, request=request)
        result, requests, identities = await self.invoke("gitee_create_file", {
            "owner": "fixture", "repo": "demo", "path": "README.md",
            "message": "Add file", "content": "safe",
        }, handler=timeout)
        self.assertTrue(result.is_error)
        self.assertEqual(len(requests), 1)
        self.assertNotIn(PAT, repr(result))
        self.assertNotIn(FRONT_TOKEN, repr(result))
        self.assertIn("unknown", repr(result).lower())
        self.assertEqual(identities, ["checked"])

    async def test_async_identity_callback_is_awaited(self):
        checked = []
        async def authorize():
            checked.append("authorized")
            return {"github_login": "offline-fixture"}
        server = FastMCP("offline-async-auth-tests", mask_error_details=True)
        api = MockAPI(lambda request: httpx2.Response(200, json={"private": True}))
        repository_tools.register_repository_tools(server, PAT, False, authorize)
        with patch.object(httpx2, "AsyncClient", api.factory):
            async with Client(server, mode="legacy") as client:
                result = await client.call_tool("gitee_get_repository", {"owner": "fixture", "repo": "demo"})
        self.assertIs(result.data["private"], True)
        self.assertEqual(checked, ["authorized"])
        self.assertEqual(len(api.requests), 1)


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    unittest.main(verbosity=2)
