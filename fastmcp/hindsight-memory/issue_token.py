"""Issue a bounded service JWT to a private file; never print the credential."""
import argparse
import base64
import hashlib
import hmac
import json
from pathlib import Path
import os
import time


def issue(secret, public, subject, days=30):
    def encode(value):
        return base64.urlsafe_b64encode(json.dumps(value, separators=(',', ':')).encode()).rstrip(b'=')
    now = int(time.time())
    message = encode({'alg': 'HS256', 'typ': 'JWT'})+b'.'+encode({
        'iss': public, 'aud': public+'/mcp', 'sub': subject,
        'iat': now, 'exp': now+days*86400, 'scope': 'memory:read memory:write'})
    return (message+b'.'+base64.urlsafe_b64encode(hmac.new(secret.encode(), message, hashlib.sha256).digest()).rstrip(b'=')).decode()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--key-file', required=True, type=Path)
    parser.add_argument('--subject', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    if args.subject not in config['principals']:
        raise SystemExit('Subject has no configured project grant')
    os.umask(0o077)
    # Do not overwrite or rotate an existing client token implicitly.
    with args.output.open('x') as file:
        file.write(issue(args.key_file.read_text().strip(), config['public_base_url'], args.subject)+'\n')
    print(json.dumps({'created': str(args.output), 'subject': args.subject, 'valid_days': 30}))
