"""Cloud API fallback when the saved environment has no usable MCP entry.

Reads one {tool, arguments, timeout_seconds?} object from stdin. No client retry.
HINDSIGHT_VPS_TOKEN can be a Cloud network-secret placeholder substituted only
on the configured HTTPS domain. Do not print the environment or request headers.
"""
import json
import hashlib
import os
import sys
import urllib.error
import urllib.request
from urllib.parse import urlsplit
from uuid import UUID, uuid4


def main():
    url = os.environ['HINDSIGHT_VPS_API_URL']
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.port not in (None, 443) or parsed.username or parsed.query or parsed.fragment:
        raise ValueError('Use the authorized HTTPS 443 API URL')
    value = json.load(sys.stdin)
    identity = {}
    if value.get('tool') == 'retain':
        arguments = value.get('arguments', {})
        if not isinstance(arguments.get('document_id'), str) or not arguments['document_id'].strip():
            raise ValueError('retain requires a stable document_id before submission')
        arguments.setdefault('operation_id', str(uuid4()))
        UUID(arguments['operation_id'])
        identity = {'operation_id': arguments['operation_id'], 'document_id': arguments['document_id'],
                    'bank_id': arguments.get('bank_id'),
                    'content_sha256': hashlib.sha256(arguments['content'].encode()).hexdigest()}
        # Emit only reconciliation identity before starting HTTP, never token/content.
        print(json.dumps({'state': 'PREPARED', **identity}), file=sys.stderr, flush=True)
    request = urllib.request.Request(url, data=json.dumps(value).encode(), method='POST',
        headers={'Authorization': 'Bearer '+os.environ['HINDSIGHT_VPS_TOKEN'], 'Content-Type': 'application/json'})
    # HTTP redirects must not send the credential to a second endpoint.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args):
            return None
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=185) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        print(json.dumps({'state': 'HTTP_ERROR', 'http_status': error.code, **identity}))
        return 1
    except (OSError, ValueError):
        print(json.dumps({'state': 'UNKNOWN', **identity, 'message': 'No client retry. Reconcile original operation on the original task.'}))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return int(result.get('isError', False))


if __name__ == '__main__':
    raise SystemExit(main())
