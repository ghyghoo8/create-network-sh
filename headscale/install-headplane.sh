#!/usr/bin/env bash
# Headplane native runtime; vendor app comes from pinned official OCI layers.
# Sources: https://headplane.net/install/native-mode
# https://github.com/tale/headplane/blob/v0.8.2/config.example.yaml
set -Eeuo pipefail
umask 027

usage() {
  cat <<'HELP'
Usage: sudo bash install-headplane.sh --check|--install

Add Headplane 0.8.2 to the existing native Headscale installation.
Requires fetch-headplane-app.py beside this script. No domain is required.
--check is read-only: no downloads, files, users, packages or services changed.
--install downloads fixed official app layers and Node 24.22.1, verifies SHA256,
then creates only the headplane account, directories and systemd service.

The UI listens on 127.0.0.1:3000 and expects the browser URL
http://127.0.0.1:13000/admin through an SSH local port forward.
Headscale configuration is read-only to this service; agent and browser SSH
are disabled. Device/user/key/route administration uses the local HTTP API.
No Headscale/ngrok/FastMCP/Hysteria restart, firewall change, migration,
backup or API key creation is performed.
HELP
}
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

if (($# != 1)); then usage; exit 2; fi
case "$1" in
  --help|-h) usage; exit 0 ;;
  --check|--install) mode="$1" ;;
  *) usage; exit 2 ;;
esac

[[ "$(uname -s)" == Linux && "$(uname -m)" == x86_64 ]] || die 'This installer requires Linux amd64.'
(( EUID == 0 )) || die 'Run with sudo or as root.'
for executable in curl python3 tar xz sha256sum ss systemctl systemd-analyze getent useradd install df awk mktemp; do
  command -v "$executable" >/dev/null || die "Missing prerequisite: $executable"
done
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
helper="$script_dir/fetch-headplane-app.py"
[[ -f "$helper" && ! -L "$helper" ]] || die 'Place the regular fetch-headplane-app.py file beside this installer.'

for path in /opt/headplane /etc/headplane /var/lib/headplane /etc/systemd/system/headplane.service /etc/systemd/system/headplane.service.d; do
  [[ ! -e "$path" && ! -L "$path" ]] || die "Existing state found: $path; inspect it instead of reinstalling."
done
[[ "$(systemctl show headplane.service -p LoadState --value)" == not-found ]] || die 'An existing headplane service is registered.'
if getent passwd headplane >/dev/null || getent group headplane >/dev/null; then
  die 'The headplane account or group already exists; inspect before installing.'
fi
getent group headscale >/dev/null || die 'The existing headscale group is required.'
systemctl is-active --quiet headscale || die 'The existing Headscale service must be active.'
[[ -f /etc/headscale/config.yaml && ! -L /etc/headscale/config.yaml ]] || die 'Expected regular /etc/headscale/config.yaml.'
public_url_json="$(python3 - <<'PY'
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
lines = [line for line in Path('/etc/headscale/config.yaml').read_text().splitlines() if line.startswith('server_url:')]
if len(lines) != 1:
    raise SystemExit('Expected one server_url in the existing Headscale configuration.')
match = re.fullmatch(r'server_url:[ \t]*"([^"\r\n]+)"[ \t]*', lines[0])
if match is None:
    raise SystemExit('Expected the quoted server_url written by the reviewed Headscale installer.')
value = match.group(1)
url = urlsplit(value)
if (url.scheme != 'https' or not url.hostname or url.netloc != url.hostname
        or url.path not in ('', '/') or url.query or url.fragment
        or not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?', url.hostname)):
    raise SystemExit('Existing server_url must be the bare HTTPS Headscale endpoint.')
print(json.dumps(value.rstrip('/')))
PY
)"
[[ -z "$(ss -H -ltn 'sport = :3000')" ]] || die 'TCP/3000 is already in use.'
available_kib="$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)"
[[ "$available_kib" =~ ^[0-9]+$ ]] && (( available_kib >= 491520 )) || die 'At least 480 MiB available memory is required for this bounded UI deployment.'
available_disk_kib="$(df -Pk /opt | awk 'NR==2 {print $4}')"
[[ "$available_disk_kib" =~ ^[0-9]+$ ]] && (( available_disk_kib >= 1048576 )) || die 'At least 1 GiB free under /opt is required.'
health_code="$(curl --noproxy '*' --connect-timeout 3 --max-time 5 -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:18080/health)"
[[ "$health_code" == 200 ]] || die 'Local Headscale HTTP/18080 health did not return 200.'
printf '%s\n' 'Preflight passed: native Headscale healthy; fresh UI state; TCP/3000 unused; memory and disk sufficient for the configured limits.'
if [[ "$mode" == --check ]]; then
  printf '%s\n' 'Read-only check finished. No files, downloads, users, packages, services or firewall rules were changed.'
  exit 0
fi

phase='prepare verified artifacts in a private temporary directory'
trap 'printf "ERROR: Headplane installation failed during %s (line %s). Existing services were not restarted; retain new state for inspection.\n" "$phase" "$LINENO" >&2' ERR
stage="$(mktemp -d /var/tmp/headplane-install.XXXXXXXX)"
cleanup() {
  if [[ "$stage" == /var/tmp/headplane-install.* && -d "$stage" && ! -L "$stage" ]]; then
    rm -rf -- "$stage"
  fi
}
trap cleanup EXIT
mkdir "$stage/runtime"
phase='download and verify official Node runtime'
node_archive="$stage/node-v24.22.1-linux-x64.tar.xz"
curl --connect-timeout 15 --max-time 300 -fL --proto '=https' --proto-redir '=https' \
  https://nodejs.org/dist/v24.22.1/node-v24.22.1-linux-x64.tar.xz -o "$node_archive"
printf '%s  %s\n' '6c172a9ab6718f7b801fb5a7bd486af2ee5e32758086a04b84fcce2aa77095e6' "$node_archive" | sha256sum --check --status
tar -xJf "$node_archive" --strip-components=1 --no-same-owner -C "$stage/runtime"
chmod -R a+rX "$stage/runtime"
[[ "$("$stage/runtime/bin/node" --version)" == v24.22.1 ]] || die 'Downloaded Node runtime version mismatch.'
rm -- "$node_archive"
phase='download and verify official Headplane application layers'
python3 "$helper" --destination "$stage/app"

phase='create only the new UI account and configuration'
mkdir -m 0755 /opt/headplane
mv -- "$stage/runtime" /opt/headplane/runtime
mv -- "$stage/app" /opt/headplane/app
useradd --system --user-group --home-dir /var/lib/headplane --no-create-home --shell /usr/sbin/nologin headplane
install -d -o root -g headplane -m 0750 /etc/headplane
install -d -o headplane -g headplane -m 0700 /var/lib/headplane
python3 - <<'PY'
import grp
import os
import secrets
path = '/etc/headplane/cookie-secret'
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
with os.fdopen(fd, 'w') as output:
    output.write(secrets.token_hex(16) + '\n')
os.chown(path, 0, grp.getgrnam('headplane').gr_gid)
PY
cat > /etc/headplane/config.yaml <<YAML
server:
  host: "127.0.0.1"
  port: 3000
  base_url: "http://127.0.0.1:13000"
  cookie_secret_path: "/etc/headplane/cookie-secret"
  cookie_secure: false
  cookie_max_age: 3600
  data_path: "/var/lib/headplane"
headscale:
  url: "http://127.0.0.1:18080"
  public_url: $public_url_json
  config_path: "/etc/headscale/config.yaml"
integration:
  agent:
    enabled: false
  docker:
    enabled: false
  kubernetes:
    enabled: false
    pod_name: "headscale"
  proc:
    enabled: true
YAML
chown root:headplane /etc/headplane/config.yaml
chmod 0640 /etc/headplane/config.yaml
cat > /etc/systemd/system/headplane.service <<'UNIT'
[Unit]
Description=Headplane private web administration
After=network.target headscale.service

[Service]
Type=simple
User=headplane
Group=headplane
SupplementaryGroups=headscale
WorkingDirectory=/opt/headplane/app
Environment=HEADPLANE_CONFIG_PATH=/etc/headplane/config.yaml
Environment=NODE_ENV=production
ExecStart=/opt/headplane/runtime/bin/node --max-old-space-size=192 /opt/headplane/app/build/server/index.js
StateDirectory=headplane
StateDirectoryMode=0700
Restart=on-failure
RestartSec=5
Nice=10
CPUQuota=50%
MemoryHigh=256M
MemoryMax=384M
MemorySwapMax=256M
TasksMax=64
NoNewPrivileges=yes
PrivateTmp=yes
ProtectHome=yes
ProtectSystem=strict
InaccessiblePaths=/var/lib/headscale /run/headscale
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
CapabilityBoundingSet=
UMask=0077

[Install]
WantedBy=multi-user.target
UNIT
phase='validate and start only the new Headplane service'
systemd-analyze verify /etc/systemd/system/headplane.service
systemctl daemon-reload
systemctl enable --now headplane
ready=0
for attempt in {1..30}; do
  ui_code="$(curl --noproxy '*' --connect-timeout 1 --max-time 2 -sS -o /dev/null -w '%{http_code}' -H 'Host: 127.0.0.1:13000' http://127.0.0.1:3000/admin 2>/dev/null || true)"
  case "$ui_code" in 200|302|303|307|308) ready=1; break ;; esac
  sleep 1
done
(( ready == 1 )) || die 'UI not ready; inspect: journalctl -u headplane -n 80 --no-pager. Do not rerun or delete state.'
systemctl is-active --quiet headplane
printf '\n%s\n' 'Headplane local HTTP entry is ready. Browser/API acceptance is still pending.'
printf '%s\n' 'No Headscale/ngrok/FastMCP/Hysteria service or firewall rule was changed.'
printf '%s\n' 'On Windows (replace VPS_SSH_HOST with the same host/IP you use for SSH):'
printf '%s\n' 'ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:13000:127.0.0.1:3000 root@VPS_SSH_HOST'
printf '%s\n' 'Keep that SSH session open. Browse exactly: http://127.0.0.1:13000/admin'
printf '%s\n' 'Create a login API key on the VPS only when ready: sudo headscale apikeys create --expiration 90d'
printf '%s\n' 'Keep the key private. Do not paste it into chat. Headscale configuration stays read-only in the UI.'
