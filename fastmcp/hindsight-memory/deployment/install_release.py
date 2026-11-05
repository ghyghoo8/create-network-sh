"""Install a reviewed release on VPS; run as root after private config setup.

No credentials are accepted on the command line. Does not alter ingress or Win.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--revision', required=True)
    args = parser.parse_args()
    if os.geteuid() != 0 or not re.fullmatch('[0-9a-f]{40}', args.revision):
        raise SystemExit('Root and a full reviewed Git commit are required')
    source = args.source.resolve()
    config = Path('/etc/hindsight-memory/config.json')
    if not config.is_file() or not Path('/etc/hindsight-memory/signing.key').is_file():
        raise SystemExit('Prepare independent private configuration/signing key first')
    subprocess.run(['/opt/hindsight-memory/venv/bin/python', '-m', 'pip', 'check'], check=True)
    try:
        account = pwd.getpwnam('hindsight-memory')
    except KeyError:
        subprocess.run(['useradd', '--system', '--home-dir', '/var/lib/hindsight-memory',
                        '--shell', '/usr/sbin/nologin', 'hindsight-memory'], check=True)
        account = pwd.getpwnam('hindsight-memory')
    root = Path('/opt/hindsight-memory')
    releases = root/'releases'
    releases.mkdir(exist_ok=True)
    release = releases/args.revision
    if release.exists():
        raise SystemExit('Release already exists; reconcile rather than overwrite')
    shutil.copytree(source, release, ignore=shutil.ignore_patterns('.git', '.venv', '__pycache__', '*.pyc'))
    for name in ('', 'oauth'):
        path = Path('/var/lib/hindsight-memory')/name
        path.mkdir(exist_ok=True, mode=0o700)
        os.chown(path, account.pw_uid, account.pw_gid)
        path.chmod(0o700)
    for path in (config.parent, config.parent/'ssh'):
        os.chown(path, 0, account.pw_gid)
        path.chmod(0o750)
    for path in (config, config.parent/'ssh/config', config.parent/'ssh/known_hosts'):
        os.chown(path, 0, account.pw_gid)
        path.chmod(0o640)
    unit = Path('/etc/systemd/system/hindsight-memory.service')
    if unit.exists():
        raise SystemExit('Service unit already exists; review the upgrade explicitly')
    shutil.copyfile(release/'deployment/hindsight-memory.service', unit)
    unit.chmod(0o644)
    current = root/'current'
    if current.exists() or current.is_symlink():
        raise SystemExit('Current release already bound; reconcile explicitly')
    current.symlink_to(release)
    manifest = {str(p.relative_to(release)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in release.rglob('*') if p.is_file()}
    (root/'deployment-receipt.json').write_text(json.dumps({
        'revision': args.revision, 'files': manifest, 'source': str(source),
        'ingress_changed': False}, indent=2)+'\n')
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', 'enable', '--now', 'hindsight-memory.service'], check=True)
    print(json.dumps({'revision': args.revision, 'release': str(release), 'service': 'hindsight-memory.service'}))


if __name__ == '__main__':
    main()
