"""Exercise HTTP authentication with OAuth enabled and an existing service JWT."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@unittest.skipUnless(importlib.util.find_spec('fastmcp'), 'Run in the locked service environment')
class MixedAuthTests(unittest.IsolatedAsyncioTestCase):
    async def test_oauth_enabled_preserves_service_jwt_and_its_scope_check(self):
        import httpx2
        import jwt
        from key_value.aio.stores.memory import MemoryStore
        import server
        from issue_token import issue
        public = 'https://example.invalid/hindsight'
        key = 'synthetic-auth-test-key-' * 3
        original = server.GitHubProvider

        def isolated_provider(**kwargs):
            return original(**kwargs, client_storage=MemoryStore())

        config = {'public_base_url': public, 'upstream': {}, 'principals': {
            'codex-cloud': {'banks': ['cf-fe-herdr-4-codexcloud'], 'mutations': ['retain']}}}
        with patch.dict('os.environ', {'HINDSIGHT_GITHUB_CLIENT_ID': 'OvSyntheticOnly',
                                     'HINDSIGHT_GITHUB_CLIENT_SECRET': 'a' * 40}), \
                patch.object(server, 'GitHubProvider', isolated_provider):
            app = server.build_app(config, key)
        valid = issue(key, public, 'codex-cloud')
        claims = jwt.decode(valid, key, algorithms=['HS256'], audience=public+'/mcp')
        claims['scope'] = 'unrelated:scope'
        wrong_scope = jwt.encode(claims, key, algorithm='HS256')
        initialize = {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
            'protocolVersion': '2025-03-26', 'capabilities': {},
            'clientInfo': {'name': 'synthetic-auth-regression', 'version': '1'}}}
        async with app.app.router.lifespan_context(app.app):
            async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app),
                                          base_url='https://example.invalid') as client:
                for token, status in [(valid, 200), (wrong_scope, 401), ('invalid', 401)]:
                    response = await client.post('/hindsight/mcp', json=initialize, headers={
                        'Authorization': 'Bearer '+token, 'Content-Type': 'application/json',
                        'Accept': 'application/json, text/event-stream'})
                    self.assertEqual(response.status_code, status, response.text)
                metadata = await client.get('/.well-known/oauth-authorization-server/hindsight')
                self.assertEqual(metadata.status_code, 200)
                self.assertIn('read:user', metadata.json()['scopes_supported'])


if __name__ == '__main__':
    unittest.main()
