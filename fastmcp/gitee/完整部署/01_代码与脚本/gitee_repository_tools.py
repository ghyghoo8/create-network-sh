"""Gitee REST tools absent from the official MCP server.

Verified against the official Gitee SDK (API v5.4.83):
https://gitee.com/sdk/gitee5j/blob/main/docs/RepositoriesApi.md
https://gitee.com/sdk/gitee5j/blob/main/docs/WebhooksApi.md
https://gitee.com/sdk/gitee5j/blob/main/docs/GitDataApi.md
https://gitee.com/sdk/gitee5j/blob/main/docs/ContentsPathBody.md
https://gitee.com/sdk/gitee5j/blob/main/docs/ContentsPathBody1.md
https://gitee.com/sdk/gitee5j/blob/main/docs/ContentsPathBody2.md
https://gitee.com/sdk/gitee5j/blob/main/docs/RepoBranchesBody.md
https://gitee.com/sdk/gitee5j/blob/main/docs/RepoCommitsBody.md
https://gitee.com/sdk/gitee5j/blob/main/docs/GitAction.md
https://gitee.com/sdk/gitee5j/blob/main/docs/RepoTagsBody.md
https://gitee.com/sdk/gitee5j/blob/main/src/main/java/com/gitee/sdk/gitee5j/auth/OAuth.java

All credentials stay in the outbound Authorization header. No redirects,
ambient proxy configuration, automatic retries, or incoming headers are used.
Write operations are exposed only in WRITE mode. Registration performs no API
calls and does not modify any repository.
"""

import base64
import binascii
import inspect
import re
from typing import Any, Literal, NotRequired, TypedDict
from urllib.parse import quote, unquote, urlsplit, urlunsplit

import httpx2
from fastmcp.exceptions import ToolError


API_BASE = "https://gitee.com/api/v5"
LOCAL_READ_TOOLS = {
    "gitee_get_repository", "gitee_list_branches", "gitee_list_commits",
    "gitee_list_tree", "gitee_list_tags", "gitee_list_hooks", "gitee_get_hook",
}
LOCAL_WRITE_TOOLS = {
    "gitee_update_repository", "gitee_delete_repository", "gitee_create_branch",
    "gitee_create_file", "gitee_update_file", "gitee_delete_file",
    "gitee_commit_files", "gitee_create_tag", "gitee_create_hook",
    "gitee_update_hook", "gitee_delete_hook", "gitee_test_hook",
}


class GitFileAction(TypedDict):
    """Documented fields accepted by Gitee's multi-file commit API."""

    action: Literal["create", "update", "delete", "move", "chmod"]
    path: str
    content: NotRequired[str]
    encoding: NotRequired[Literal["text", "base64"]]
    previous_path: NotRequired[str]
    last_commit_id: NotRequired[str]
    execute_filemode: NotRequired[bool]


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ToolError(f"{label} must be a nonempty string without control characters.")
    return value


def _segment(value: str, label: str) -> str:
    value = _text(value, label)
    decoded = value
    for _ in range(8):
        newer = unquote(decoded)
        if newer == decoded:
            break
        decoded = newer
    if decoded in {".", ".."} or "/" in decoded or "\\" in decoded or decoded != decoded.strip():
        raise ToolError(f"{label} must be a single path segment without traversal.")
    if any(ord(c) < 32 or ord(c) == 127 for c in decoded):
        raise ToolError(f"{label} must not contain encoded control characters.")
    return quote(value, safe="")


def _path(value: str) -> str:
    value = _text(value, "path")
    return "/".join(_segment(part, "path component") for part in value.split("/"))


def _ref(value: str, label: str = "ref") -> str:
    value = _text(value, label)
    # Slash-containing refs are valid Git names; encode the complete ref when it
    # occupies one API path parameter, while checking each original component.
    for part in value.split("/"):
        _segment(part, label)
    if ".." in value or "@{" in value or any(c in value for c in " ~^:?*[\\") or value.endswith("."):
        raise ToolError(f"{label} must be a valid branch, tag, or commit reference.")
    return quote(value, safe="")


def _repo_path(owner: str, repo: str) -> str:
    return "/repos/" + _segment(owner, "owner") + "/" + _segment(repo, "repo")


def _pagination(page: int, per_page: int) -> dict[str, int]:
    if isinstance(page, bool) or not isinstance(page, int) or page < 1:
        raise ToolError("page must be a positive integer.")
    if isinstance(per_page, bool) or not isinstance(per_page, int) or not 1 <= per_page <= 100:
        raise ToolError("per_page must be between 1 and 100.")
    return {"page": page, "per_page": per_page}


def _sha(value: str, label: str = "sha") -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-fA-F]{40}", value) is None:
        if label == "last_commit_id":
            raise ToolError("last_commit_id must be the file's latest 40-character commit SHA.")
        raise ToolError("sha must be the current 40-character file Blob SHA from get_file_content.")
    return value


def _content(value: str, encoding: str) -> str:
    if not isinstance(value, str):
        raise ToolError("content must be a string.")
    if encoding == "utf8":
        try:
            return base64.b64encode(value.encode("utf-8")).decode("ascii")
        except UnicodeError:
            raise ToolError("content must be valid UTF-8 text.") from None
    if encoding == "base64":
        try:
            compact = "".join(value.split())
            raw = base64.b64decode(compact, validate=True)
            return base64.b64encode(raw).decode("ascii")
        except (ValueError, binascii.Error, UnicodeError):
            raise ToolError("content must be valid base64 when encoding is base64.") from None
    raise ToolError("encoding must be utf8 or base64.")


def _git_user(value: dict[str, str] | None, label: str) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, dict) or not value or set(value) - {"name", "email"}:
        raise ToolError(f"{label} may contain only name and email.")
    return {key: _text(item, label) for key, item in value.items()}


def _without_none(values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}


def _hook_id(value: int) -> str:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ToolError("hook_id must be a positive integer.")
    return str(value)


def _hook_url(value: str) -> str:
    value = _text(value, "url")
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError
        parsed.port
    except ValueError:
        raise ToolError("url must be an HTTP or HTTPS webhook URL without embedded credentials.") from None
    return value


def _redact_hooks(value: Any) -> Any:
    if isinstance(value, dict):
        output = {}
        for key, item in value.items():
            if any(part in str(key).lower() for part in ("password", "secret", "token", "authorization")):
                output[key] = "[REDACTED]"
            elif str(key).lower() == "url" and isinstance(item, str):
                try:
                    parsed = urlsplit(item)
                    # Query parameters and URL credentials may contain callback
                    # secrets. Keep a useful destination without those values.
                    authority = parsed.netloc.rsplit("@", 1)[-1]
                    output[key] = urlunsplit((parsed.scheme, authority, parsed.path, "", ""))
                except ValueError:
                    output[key] = "[REDACTED]"
            else:
                output[key] = _redact_hooks(item)
        return output
    if isinstance(value, list):
        return [_redact_hooks(item) for item in value]
    return value


class _GiteeAPI:
    def __init__(self, pat: str, identity_check):
        self.pat = pat
        self.identity_check = identity_check

    async def request(self, method: str, path: str, *, params=None, body=None, webhook=False):
        try:
            verified = self.identity_check()
            if inspect.isawaitable(verified):
                await verified
        except Exception:
            raise ToolError("The authenticated gateway identity is not permitted.") from None
        writing = method != "GET"
        try:
            async with httpx2.AsyncClient(
                headers={"Authorization": "Bearer " + self.pat, "Accept": "application/json"},
                auth=None, trust_env=False, follow_redirects=False, timeout=30.0,
            ) as client:
                response = await client.request(
                    method, API_BASE + path, params=params,
                    json=body if body is not None else None,
                )
        except Exception:
            suffix = (
                " The write outcome is unknown; check repository or webhook state before retrying."
                if writing else " Check Gitee upstream connectivity."
            )
            raise ToolError("Gitee API request did not complete." + suffix) from None
        if not 200 <= response.status_code < 300:
            suffix = (
                " Check repository or webhook state before retrying this write."
                if writing else " Check token permissions and the requested repository or reference."
            )
            # Upstream response bodies, URLs, and headers can echo secrets.
            raise ToolError(f"Gitee API returned HTTP {response.status_code}." + suffix) from None
        if not response.content:
            return {"status": "ok", "http_status": response.status_code}
        try:
            result = response.json()
        except Exception:
            suffix = " The write may have completed; check state before retrying." if writing else ""
            raise ToolError("Gitee API returned an invalid JSON response." + suffix) from None
        return _redact_hooks(result) if webhook else result


def register_repository_tools(mcp, pat: str, write_mode: bool, identity_check) -> set[str]:
    """Register authorized REST tools and return their exact advertised names."""
    api = _GiteeAPI(pat, identity_check)
    registered: set[str] = set()

    def tool(*, read: bool, destructive: bool = False):
        def register(func):
            if read or write_mode:
                mcp.tool(annotations={
                    "readOnlyHint": read, "destructiveHint": destructive,
                    "idempotentHint": read, "openWorldHint": True,
                })(func)
                registered.add(func.__name__)
            return func
        return register

    @tool(read=True)
    async def gitee_get_repository(owner: str, repo: str) -> Any:
        """Get metadata, visibility, default branch, and permissions of one repository."""
        return await api.request("GET", _repo_path(owner, repo))

    @tool(read=False, destructive=True)
    async def gitee_update_repository(
        owner: str, repo: str, name: str, description: str | None = None,
        homepage: str | None = None, private: bool | None = None,
        default_branch: str | None = None, path: str | None = None,
        has_issues: bool | None = None, has_wiki: bool | None = None,
        online_edit_enabled: bool | None = None, pull_requests_enabled: bool | None = None,
        default_merge_method: Literal["merge", "squash", "rebase"] | None = None,
    ) -> Any:
        """Update repository settings. Supply the current name to keep it; private=false makes code public."""
        destination = _repo_path(owner, repo)
        _text(name, "name")
        if path is not None:
            _segment(path, "new repository path")
        if default_branch is not None:
            _ref(default_branch, "default_branch")
        body = _without_none({
            "name": name, "description": description, "homepage": homepage,
            "private": private, "default_branch": default_branch, "path": path,
            "has_issues": has_issues, "has_wiki": has_wiki,
            "online_edit_enabled": online_edit_enabled, "pull_requests_enabled": pull_requests_enabled,
            "default_merge_method": default_merge_method,
        })
        return await api.request("PATCH", destination, body=body)

    @tool(read=False, destructive=True)
    async def gitee_delete_repository(owner: str, repo: str) -> Any:
        """Permanently delete the specified repository, including its history and collaboration data."""
        return await api.request("DELETE", _repo_path(owner, repo))

    @tool(read=True)
    async def gitee_list_branches(
        owner: str, repo: str, page: int = 1, per_page: int = 20,
        sort: Literal["name", "updated"] = "name",
        direction: Literal["asc", "desc"] = "asc",
    ) -> Any:
        """List branches in a repository."""
        return await api.request("GET", _repo_path(owner, repo) + "/branches", params=_pagination(page, per_page) | {"sort": sort, "direction": direction})

    @tool(read=False)
    async def gitee_create_branch(owner: str, repo: str, branch_name: str, refs: str) -> Any:
        """Create a branch from an existing branch, tag, or commit reference."""
        _ref(branch_name, "branch_name")
        _ref(refs, "refs")
        return await api.request("POST", _repo_path(owner, repo) + "/branches", body={"branch_name": branch_name, "refs": refs})

    @tool(read=True)
    async def gitee_list_commits(
        owner: str, repo: str, sha: str | None = None, path: str | None = None,
        author: str | None = None, since: str | None = None, until: str | None = None,
        page: int = 1, per_page: int = 20,
    ) -> Any:
        """List commits, optionally filtered by branch/ref, file, author, and ISO 8601 time range."""
        if sha is not None:
            _ref(sha, "sha")
        if path is not None:
            _path(path)
        params = _pagination(page, per_page) | _without_none({"sha": sha, "path": path, "author": author, "since": since, "until": until})
        return await api.request("GET", _repo_path(owner, repo) + "/commits", params=params)

    @tool(read=True)
    async def gitee_list_tree(owner: str, repo: str, sha: str, recursive: bool = False) -> Any:
        """List a repository tree at a branch, commit, or tree SHA; recursive=true includes nested entries."""
        return await api.request("GET", _repo_path(owner, repo) + "/git/trees/" + _ref(sha, "sha"), params={"recursive": 1 if recursive else 0})

    @tool(read=True)
    async def gitee_list_tags(
        owner: str, repo: str, page: int = 1, per_page: int = 20,
        sort: Literal["name", "updated"] = "name",
        direction: Literal["asc", "desc"] = "asc",
    ) -> Any:
        """List repository tags."""
        return await api.request("GET", _repo_path(owner, repo) + "/tags", params=_pagination(page, per_page) | {"sort": sort, "direction": direction})

    @tool(read=False)
    async def gitee_create_tag(owner: str, repo: str, tag_name: str, refs: str, tag_message: str | None = None) -> Any:
        """Create a tag from an existing branch or commit reference."""
        _ref(tag_name, "tag_name")
        _ref(refs, "refs")
        return await api.request("POST", _repo_path(owner, repo) + "/tags", body=_without_none({"tag_name": tag_name, "refs": refs, "tag_message": tag_message}))

    def file_body(message, branch, author, committer):
        _text(message, "message")
        if branch is not None:
            _ref(branch, "branch")
        return _without_none({"message": message, "branch": branch, "author": _git_user(author, "author"), "committer": _git_user(committer, "committer")})

    @tool(read=False)
    async def gitee_create_file(
        owner: str, repo: str, path: str, message: str, content: str,
        encoding: Literal["utf8", "base64"] = "utf8", branch: str | None = None,
        author: dict[str, str] | None = None, committer: dict[str, str] | None = None,
    ) -> Any:
        """Create a new file and commit it. Use base64 for binary bytes; omitted branch uses the default branch."""
        body = file_body(message, branch, author, committer) | {"content": _content(content, encoding)}
        return await api.request("POST", _repo_path(owner, repo) + "/contents/" + _path(path), body=body)

    @tool(read=False, destructive=True)
    async def gitee_update_file(
        owner: str, repo: str, path: str, message: str, content: str, sha: str,
        encoding: Literal["utf8", "base64"] = "utf8", branch: str | None = None,
        author: dict[str, str] | None = None, committer: dict[str, str] | None = None,
    ) -> Any:
        """Update a file and commit it, requiring its current Blob SHA to guard against a stale overwrite."""
        body = file_body(message, branch, author, committer) | {"content": _content(content, encoding), "sha": _sha(sha)}
        return await api.request("PUT", _repo_path(owner, repo) + "/contents/" + _path(path), body=body)

    @tool(read=False, destructive=True)
    async def gitee_delete_file(
        owner: str, repo: str, path: str, message: str, sha: str,
        branch: str | None = None, author: dict[str, str] | None = None,
        committer: dict[str, str] | None = None,
    ) -> Any:
        """Delete one file and commit it, requiring its current Blob SHA."""
        body = file_body(message, branch, author, committer) | {"sha": _sha(sha)}
        return await api.request("DELETE", _repo_path(owner, repo) + "/contents/" + _path(path), body=body)

    @tool(read=False, destructive=True)
    async def gitee_commit_files(
        owner: str, repo: str, branch: str, message: str,
        actions: list[GitFileAction], start_branch: str | None = None,
        author: dict[str, str] | None = None,
    ) -> Any:
        """Commit multiple file actions together. Actions use action=create/update/delete/move/chmod, path, optional content, encoding=text/base64, previous_path, last_commit_id, execute_filemode. Use last_commit_id for update/delete/move to protect against stale edits. New branches require start_branch."""
        _ref(branch, "branch")
        _text(message, "message")
        if start_branch is not None:
            _ref(start_branch, "start_branch")
        if not isinstance(actions, list) or not actions:
            raise ToolError("actions must contain at least one file action.")
        checked = []
        allowed = {"action", "path", "content", "encoding", "previous_path", "last_commit_id", "execute_filemode"}
        for action in actions:
            if not isinstance(action, dict) or set(action) - allowed:
                raise ToolError("Each file action must use the documented action fields only.")
            kind = action.get("action")
            if kind not in {"create", "update", "delete", "move", "chmod"}:
                raise ToolError("Invalid file action; use create, update, delete, move, or chmod.")
            _path(action.get("path"))
            entry = dict(action)
            if kind in {"create", "update"} and "content" not in entry:
                raise ToolError("Create and update file actions require content.")
            if kind == "move" and "previous_path" not in entry:
                raise ToolError("Move file actions require previous_path.")
            if "previous_path" in entry:
                _path(entry["previous_path"])
            if "last_commit_id" in entry:
                _sha(entry["last_commit_id"], "last_commit_id")
            if "execute_filemode" in entry and type(entry["execute_filemode"]) is not bool:
                raise ToolError("execute_filemode must be a boolean.")
            if "encoding" in entry and entry["encoding"] not in {"text", "base64"}:
                raise ToolError("File action encoding must be text or base64.")
            if "content" in entry:
                encoding = entry.get("encoding", "text")
                if encoding == "base64":
                    entry["content"] = _content(entry["content"], "base64")
                else:
                    _content(entry["content"], "utf8")
            checked.append(entry)
        body = _without_none({"branch": branch, "message": message, "actions": checked, "start_branch": start_branch, "author": _git_user(author, "author")})
        return await api.request("POST", _repo_path(owner, repo) + "/commits", body=body)

    @tool(read=True)
    async def gitee_list_hooks(owner: str, repo: str, page: int = 1, per_page: int = 20) -> Any:
        """List repository webhooks, omitting returned secrets and URL credentials/query values."""
        return await api.request("GET", _repo_path(owner, repo) + "/hooks", params=_pagination(page, per_page), webhook=True)

    @tool(read=True)
    async def gitee_get_hook(owner: str, repo: str, hook_id: int) -> Any:
        """Get one repository webhook, omitting returned secrets and URL credentials/query values."""
        return await api.request("GET", _repo_path(owner, repo) + "/hooks/" + _hook_id(hook_id), webhook=True)

    def hook_body(url, password, encryption_type, push_events, tag_push_events, issues_events, note_events, merge_requests_events):
        _hook_url(url)
        if encryption_type not in {None, 0, 1} or isinstance(encryption_type, bool):
            raise ToolError("encryption_type must be 0 (password) or 1 (signing key).")
        return _without_none({"url": url, "password": password, "encryption_type": encryption_type, "push_events": push_events, "tag_push_events": tag_push_events, "issues_events": issues_events, "note_events": note_events, "merge_requests_events": merge_requests_events})

    @tool(read=False)
    async def gitee_create_hook(
        owner: str, repo: str, url: str, password: str | None = None,
        encryption_type: Literal[0, 1] | None = None, push_events: bool = True,
        tag_push_events: bool = False, issues_events: bool = False,
        note_events: bool = False, merge_requests_events: bool = False,
    ) -> Any:
        """Create a repository webhook. The destination receives selected repository events; password stays out of returned output."""
        body = hook_body(url, password, encryption_type, push_events, tag_push_events, issues_events, note_events, merge_requests_events)
        return await api.request("POST", _repo_path(owner, repo) + "/hooks", body=body, webhook=True)

    @tool(read=False, destructive=True)
    async def gitee_update_hook(
        owner: str, repo: str, hook_id: int, url: str, password: str | None = None,
        encryption_type: Literal[0, 1] | None = None, push_events: bool | None = None,
        tag_push_events: bool | None = None, issues_events: bool | None = None,
        note_events: bool | None = None, merge_requests_events: bool | None = None,
    ) -> Any:
        """Update a webhook destination/settings; omitted optional fields remain unchanged. Supply its current URL to keep the destination."""
        body = hook_body(url, password, encryption_type, push_events, tag_push_events, issues_events, note_events, merge_requests_events)
        return await api.request("PATCH", _repo_path(owner, repo) + "/hooks/" + _hook_id(hook_id), body=body, webhook=True)

    @tool(read=False, destructive=True)
    async def gitee_delete_hook(owner: str, repo: str, hook_id: int) -> Any:
        """Delete one repository webhook."""
        return await api.request("DELETE", _repo_path(owner, repo) + "/hooks/" + _hook_id(hook_id), webhook=True)

    @tool(read=False, destructive=True)
    async def gitee_test_hook(owner: str, repo: str, hook_id: int) -> Any:
        """Send a webhook test request to its configured destination, which may trigger downstream actions."""
        return await api.request("POST", _repo_path(owner, repo) + "/hooks/" + _hook_id(hook_id) + "/tests", webhook=True)

    return registered
