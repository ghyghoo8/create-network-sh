"""Independent HTTPS MCP/API front door for the existing Win Hindsight."""
import asyncio
from copy import deepcopy
import json
import logging
import os
from pathlib import Path
from urllib.parse import urlsplit

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.auth import MultiAuth
from fastmcp.server.auth.providers.github import GitHubProvider
from fastmcp.server.auth.providers.jwt import JWTVerifier
from fastmcp.server.dependencies import get_access_token
from fastmcp.tools import Tool, ToolResult
from mcp.types import ToolAnnotations
from starlette.responses import JSONResponse

from adapter import API_TOOLS, Gateway, MAX_MESSAGE, SSHTransport


def build_app(config, secret):
    public = config['public_base_url'].rstrip('/')
    url = urlsplit(public)
    if url.scheme != 'https' or not url.netloc or url.query or url.fragment or url.username:
        raise ValueError('A dedicated HTTPS public base URL is required')
    if len(secret) < 43:
        raise ValueError('Independent signing key must contain at least 32 random bytes')
    verifier = JWTVerifier(public_key=secret, issuer=public, audience=public+'/mcp', algorithm='HS256')
    oauth = None
    if os.environ.get('HINDSIGHT_GITHUB_CLIENT_ID'):
        oauth = GitHubProvider(
            client_id=os.environ['HINDSIGHT_GITHUB_CLIENT_ID'],
            client_secret=os.environ['HINDSIGHT_GITHUB_CLIENT_SECRET'],
            base_url=public, issuer_url=public, resource_base_url=public,
            redirect_path='/auth/callback', required_scopes=['read:user'],
            jwt_signing_key=secret, require_authorization_consent=True)
    auth = MultiAuth(server=oauth, verifiers=[verifier], base_url=public, resource_base_url=public)
    catalog = json.loads((Path(__file__).parent/'catalog.json').read_text())
    gateway = Gateway(SSHTransport(config['upstream']), catalog)
    slots = asyncio.Semaphore(2)
    server = FastMCP('Hindsight Project Memory', auth=auth, mask_error_details=True,
                    instructions='Project-shared memory only. Use explicit authorized project bank IDs. '
                    'Preserve source/document/operation IDs. Async accepted is not extraction completed. '
                    'VPS owns retries. Unavailable memory does not block tasks with sufficient original inputs.')

    def grant(token, tool):
        if token is None:
            raise PermissionError('Authentication required')
        login = (token.claims or {}).get('login')
        principal = 'github:'+login.casefold() if isinstance(login, str) else token.subject
        policy = config['principals'].get(principal)
        if not policy:
            raise PermissionError('Principal is not authorized')
        readonly = gateway.catalog[tool].get('annotations', {}).get('readOnlyHint') is True
        if not readonly and tool not in policy.get('mutations', []):
            raise PermissionError('Mutation is not authorized')
        return policy['banks']

    async def invoke(token, tool, arguments, protocol='mcp', timeout=180):
        if tool not in gateway.catalog:
            raise ValueError('Unknown tool')
        banks = grant(token, tool)
        # Queue wait is bounded separately; no permanent queue or retry loop.
        try:
            await asyncio.wait_for(slots.acquire(), .1)
        except TimeoutError:
            return {'content': [{'type': 'text', 'text': 'BUSY: no upstream action started'}], 'isError': True}
        try:
            return await gateway.invoke(tool, arguments, allowed_banks=banks,
                                        protocol=protocol, timeout=timeout)
        finally:
            slots.release()

    class ForwardTool(Tool):
        async def run(self, arguments):
            try:
                result = await invoke(get_access_token(), self.name, arguments)
            except (ValueError, PermissionError) as error:
                raise ToolError(str(error)) from None
            return ToolResult(content=result.get('content', []),
                              structured_content=result.get('structuredContent'),
                              meta=result.get('_meta'), is_error=result.get('isError', False))

    for item in catalog['tools']:
        schema = deepcopy(item['inputSchema'])
        description = item.get('description')
        if item['name'] == 'retain':
            schema['required'] = list(dict.fromkeys(schema['required']+['document_id', 'operation_id']))
            description = ('Contribute source-bearing project experience. Allocate operation_id UUID and stable '
                           'document_id before sending. Preserve IDs and exact payload on uncertain results. '
                           'Accepted is async admission, not extraction completion.')
        server.add_tool(ForwardTool(name=item['name'], title=item.get('title'),
                                   description=description, parameters=schema,
                                   # Gateway may return explicit UNKNOWN/BUSY instead of the native success shape.
                                   output_schema=None,
                                   annotations=ToolAnnotations(**item.get('annotations', {}))))

    @server.custom_route('/api', methods=['POST'])
    async def api(request):
        header = request.headers.get('authorization', '')
        token = await auth.verify_token(header[7:]) if header.startswith('Bearer ') else None
        if token is None:
            return JSONResponse({'error': 'unauthorized'}, status_code=401)
        if not request.headers.get('content-type', '').startswith('application/json'):
            return JSONResponse({'error': 'JSON required'}, status_code=415)
        try:
            value = await request.json()
            if not isinstance(value, dict) or value.keys()-{'tool', 'arguments', 'timeout_seconds'}:
                raise ValueError('Expected tool, arguments and optional timeout_seconds')
            if value.get('tool') not in API_TOOLS:
                raise ValueError('Tool is not supported by the API relay')
            result = await invoke(token, value['tool'], value.get('arguments', {}), 'api',
                                  value.get('timeout_seconds', 180))
            return JSONResponse(result)
        except PermissionError:
            return JSONResponse({'error': 'forbidden'}, status_code=403)
        except (ValueError, KeyError):
            return JSONResponse({'error': 'invalid request'}, status_code=400)

    return PublicPrefix(server.http_app(path='/mcp', stateless_http=True, json_response=True),
                        url.path, url.scheme+'://'+url.netloc)


class PublicPrefix:
    def __init__(self, app, prefix, origin):
        self.app, self.prefix, self.origin = app, prefix, origin

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        headers = dict(scope.get('headers', []))
        origin = headers.get(b'origin')
        if origin and origin.decode() != self.origin:
            return await JSONResponse({'error': 'origin denied'}, 403)(scope, receive, send)
        try:
            length = int(headers.get(b'content-length', b'0'))
        except ValueError:
            length = MAX_MESSAGE+1
        if length > MAX_MESSAGE:
            return await JSONResponse({'error': 'message too large'}, 413)(scope, receive, send)
        path = scope['path']
        if path.startswith(self.prefix+'/'):
            path = path[len(self.prefix):]
        elif path == '/.well-known/oauth-authorization-server'+self.prefix:
            path = '/.well-known/oauth-authorization-server'
        elif path != '/.well-known/oauth-protected-resource'+self.prefix+'/mcp':
            return await JSONResponse({'error': 'not found'}, 404)(scope, receive, send)
        consumed = 0

        async def bounded_receive():
            nonlocal consumed
            message = await receive()
            consumed += len(message.get('body', b''))
            if consumed > MAX_MESSAGE:
                # Fixed transport bound also applies to chunked clients.
                raise ValueError('message too large')
            return message

        await self.app({**scope, 'path': path, 'raw_path': path.encode()}, bounded_receive, send)


if __name__ == '__main__':
    import uvicorn
    os.umask(0o077)
    config = json.loads(Path(os.environ['HINDSIGHT_VPS_CONFIG']).read_text())
    secret = Path(os.environ['HINDSIGHT_VPS_SIGNING_KEY_FILE']).read_text().strip()
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    logging.getLogger('fastmcp').setLevel(logging.WARNING)
    uvicorn.run(build_app(config, secret), host='127.0.0.1', port=8767,
                access_log=False, log_level='warning', log_config=None)
