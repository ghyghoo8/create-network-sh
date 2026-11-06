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


@unittest.skipUnless(importlib.util.find_spec('fastmcp'), 'Run in the locked service environment')
class ProjectBankGrantTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.public = 'https://example.invalid/hindsight'
        self.key = 'synthetic-project-grant-key-' * 3
        self.config = {'public_base_url': self.public, 'upstream': {}, 'principals': {
            'github:ghyghoo8': {'banks': ['cf-fe-herdr-4-codexcloud'],
                               'all_project_banks': True, 'mutations': ['retain']},
            'codex-cloud': {'banks': ['cf-fe-herdr-4-codexcloud'], 'mutations': ['retain']}}}

    async def test_all_project_banks_preserves_identity_and_mutation_boundaries(self):
        import httpx2
        import jwt
        import adapter
        import server
        from issue_token import issue

        calls = []

        async def fake_call(transport, protocol, tool, arguments, timeout, trace):
            calls.append((protocol, tool, arguments))
            if tool == 'retain':
                return adapter.result_body({'status': 'accepted',
                                            'operation_id': arguments['operation_id']})
            return adapter.result_body({'results': []})

        # Synthetic verified claims exercise principal routing; no external OAuth exchange.
        service_token = issue(self.key, self.public, 'codex-cloud')
        claims = jwt.decode(service_token, self.key, algorithms=['HS256'],
                            audience=self.public+'/mcp')
        claims['login'] = 'GHYGHOO8'
        github_token = jwt.encode(claims, self.key, algorithm='HS256')
        claims['login'] = 'not-authorized'
        unknown_token = jwt.encode(claims, self.key, algorithm='HS256')
        future_bank = 'future-project-not-in-startup-list'

        with patch.dict('os.environ', {'HINDSIGHT_GITHUB_CLIENT_ID': ''}), \
                patch.object(server.SSHTransport, 'call', fake_call):
            app = server.build_app(self.config, self.key)
            async with app.app.router.lifespan_context(app.app):
                async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app),
                                              base_url='https://example.invalid') as client:
                    response = await client.post('/hindsight/api', json={
                        'tool': 'recall', 'arguments': {'bank_id': future_bank, 'query': 'synthetic'}},
                        headers={'Authorization': 'Bearer '+github_token})
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertFalse(response.json()['isError'])
                    self.assertEqual([(protocol, tool) for protocol, tool, _ in calls],
                                     [('api', 'recall')])
                    self.assertEqual(calls[-1][2]['bank_id'], future_bank)

                    operation = 'c9a0e8a9-3e2b-4d94-88cd-58e5e8380939'
                    response = await client.post('/hindsight/api', json={
                        'tool': 'retain', 'arguments': {'bank_id': future_bank,
                            'content': 'Synthetic source-bearing test; never sent to Hindsight.',
                            'document_id': 'synthetic-permission-test', 'operation_id': operation}},
                        headers={'Authorization': 'Bearer '+github_token})
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertFalse(response.json()['isError'])
                    self.assertEqual(response.json()['_meta']['hindsight_gateway']['write_state'],
                                     'SUBMITTED')
                    self.assertEqual(calls[-1][1], 'retain')
                    self.assertEqual(calls[-1][2]['operation_id'], operation)

                    for token in (service_token, unknown_token):
                        with self.subTest(principal='service' if token == service_token else 'unknown'):
                            count = len(calls)
                            response = await client.post('/hindsight/api', json={
                                'tool': 'recall',
                                'arguments': {'bank_id': future_bank, 'query': 'synthetic'}},
                                headers={'Authorization': 'Bearer '+token})
                            self.assertEqual(response.status_code, 403, response.text)
                            self.assertEqual(len(calls), count)

                    for tool in ('delete_bank', 'delete_document', 'clear_memories',
                                 'create_bank', 'update_bank'):
                        with self.subTest(tool=tool):
                            arguments = {'bank_id': future_bank}
                            if tool == 'delete_document':
                                arguments['document_id'] = 'synthetic-permission-test'
                            count = len(calls)
                            response = await client.post('/hindsight/mcp', json={
                                'jsonrpc': '2.0', 'id': tool, 'method': 'tools/call',
                                'params': {'name': tool, 'arguments': arguments}}, headers={
                                    'Authorization': 'Bearer '+github_token,
                                    'Content-Type': 'application/json',
                                    'Accept': 'application/json, text/event-stream',
                                    'MCP-Protocol-Version': '2025-03-26'})
                            self.assertEqual(response.status_code, 200, response.text)
                            result = response.json()['result']
                            self.assertTrue(result['isError'])
                            self.assertIn('Mutation is not authorized',
                                          str(result['content']))
                            self.assertEqual(len(calls), count)

    async def test_all_project_banks_requires_json_boolean(self):
        import server

        with patch.dict('os.environ', {'HINDSIGHT_GITHUB_CLIENT_ID': ''}):
            for value in ('true', 'false', 0, 1, None, [], {}):
                with self.subTest(value=value):
                    self.config['principals']['github:ghyghoo8']['all_project_banks'] = value
                    with self.assertRaises(ValueError):
                        server.build_app(self.config, self.key)


if __name__ == '__main__':
    unittest.main()
