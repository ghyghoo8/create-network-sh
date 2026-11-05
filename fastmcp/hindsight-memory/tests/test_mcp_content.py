"""Native content must remain content, not JSON-encoded a second time."""
import importlib.util
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@unittest.skipUnless(importlib.util.find_spec('fastmcp'), 'Run in the locked service environment')
class MCPContentTests(unittest.TestCase):
    def test_preserves_text_structured_result_and_gateway_meta(self):
        from server import tool_result
        result = tool_result({'content': [{'type': 'text', 'text': '{"banks": []}'}],
                              'structuredContent': {'banks': []}, 'isError': False,
                              '_meta': {'hindsight_gateway': {'request_id': 'one-original-call'}}})
        self.assertEqual(result.content[0].text, '{"banks": []}')
        self.assertEqual(result.structured_content, {'banks': []})
        self.assertEqual(result.meta['hindsight_gateway']['request_id'], 'one-original-call')


if __name__ == '__main__':
    unittest.main()
