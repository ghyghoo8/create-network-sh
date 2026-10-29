"""Offline policy/schema/header tests; no secrets, network, or real OAuth."""
import ast
import asyncio
import copy
import json
import types
import unittest
from pathlib import Path
from jsonschema import validate
from auth_policy import allowed_identity, identity_result

source = ast.parse(Path(__file__).with_name('gateway_server.py').read_text())
selected = [n for n in source.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in {'private_arguments', 'make_transport', 'SafeUpstreamErrors'}]
class CapturedClient:
    def __init__(self, **kwargs): self.options = kwargs
class CapturedTransport:
    def __init__(self, url, **kwargs): self.url, self.options = url, kwargs
class Result:
    def __init__(self, **kwargs): self.__dict__.update(kwargs)
ns = dict(validate=validate, httpx2=types.SimpleNamespace(AsyncClient=CapturedClient),
          StreamableHttpTransport=CapturedTransport, READ_TOOLS={'get_user_info','list_user_repos','get_file_content'},
          UPSTREAM='https://api.gitee.com/mcp', Middleware=object, ToolResult=Result)
exec(compile(ast.Module(body=selected, type_ignores=[]), '<tested-functions>', 'exec'), ns)
SCHEMA = {'type':'object','properties':{'private':{'type':'boolean'}, 'owner_type':{'type':'string','enum':['user','org']},
          'name':{'type':'string'},'path':{'type':'string'},'auto_init':{'type':'boolean'}},
          'required':['owner_type','name']}

class Tests(unittest.TestCase):
    def test_missing_wrong_identity(self):
        for token in [None, types.SimpleNamespace(claims={}), types.SimpleNamespace(claims={'login':'other'})]:
            self.assertIsNone(allowed_identity(token))
            with self.assertRaises(PermissionError): identity_result(token)
    def test_correct_identity(self):
        self.assertEqual(identity_result(types.SimpleNamespace(claims={'login':'your-github-login'}))['status'],'ok')
    def test_private_fixed_arguments(self):
        a=ns['private_arguments'](types.SimpleNamespace(input_schema=SCHEMA))
        self.assertEqual(a,{'owner_type':'user','name':'a-share-investment-engine','path':'a-share-investment-engine','private':True,'auto_init':False})
    def test_schema_drift_rejected(self):
        for transform in [lambda s:s['properties'].pop('private'), lambda s:s['required'].append('new_required'),
                          lambda s:s['properties']['private'].update(const=False),
                          lambda s:s['properties']['name'].update(pattern='^different$')]:
            s=copy.deepcopy(SCHEMA);transform(s)
            with self.assertRaises(Exception):ns['private_arguments'](types.SimpleNamespace(input_schema=s))
    def test_header_isolation(self):
        t=ns['make_transport']('synthetic-test-marker',False)
        c=t.options['httpx_client_factory'](headers={'Authorization':'incoming-test-marker','Cookie':'incoming'},auth='incoming',follow_redirects=True)
        self.assertEqual(t.url,'https://api.gitee.com/mcp')
        self.assertEqual(set(c.options['headers']),{'Authorization','X-MCP-Enabled-Tools'})
        self.assertEqual(c.options['headers']['Authorization'],'Bearer synthetic-test-marker')
        self.assertIsNone(c.options['auth']);self.assertFalse(c.options['follow_redirects']);self.assertFalse(c.options['trust_env'])
        self.assertNotIn('create_repo',c.options['headers']['X-MCP-Enabled-Tools'])
    def test_write_header_bounded(self):
        t=ns['make_transport']('synthetic-test-marker',True)
        self.assertEqual(set(t.options['headers']['X-MCP-Enabled-Tools'].split(',')),ns['READ_TOOLS']|{'create_repo'})
    def test_error_payload_masked(self):
        async def bad(_): return Result(is_error=True,content='untrusted error details')
        result=asyncio.run(ns['SafeUpstreamErrors']().on_call_tool(None,bad))
        self.assertTrue(result.is_error);self.assertNotIn('untrusted',result.content)

if __name__=='__main__':unittest.main()
