#!/usr/bin/env bash
# Fresh shared-ngrok preparation only. Existing services and tunnels are untouched.
# Fixed release digests and evidence boundaries: headscale/sources.md.
set -Eeuo pipefail
umask 077

usage() {
    cat <<'USAGE'
Usage: bash headscale/rebuild.sh --check | --install | --help

Required process environment variable:
  HEADSCALE_HOSTNAME  Existing ngrok bare hostname already used by FastMCP.

--check    Read-only Linux/root preflight and local unauthenticated MCP probe.
--install  Preflight, verify pinned downloads, install only Headscale and its
           independent local Caddy ingress, then start these two new services.
--help     Show this help; requires no variable, root, or Linux.

The script never reads or executes an .env file. Set HEADSCALE_HOSTNAME explicitly
in the process environment (with sudo, use sudo env HEADSCALE_HOSTNAME=... bash
headscale/rebuild.sh --check). Replace the reserved example in config.env.example.
Supply a lowercase ASCII bare hostname, without https://, a port, or a path.

Target: Debian >=12 or Ubuntu >=22.04, amd64/arm64, systemd, fresh Headscale.
Local TCP/18080, TCP/19080 and TCP/50443 must be unused. Existing FastMCP must
return HTTP 401 at 127.0.0.1:8765/mcp with the original hostname in its Host header.
No TCP/443 or UDP listener is added. Hysteria UDP/443 is never inspected or changed.

Prepared routing: manually repoint the existing ngrok tunnel to local port 19080;
Caddy sends selected Headscale paths to 18080 and all remaining paths to FastMCP
8765. /auth/callback always belongs to FastMCP. No /headscale prefix is added.
TLS stays at ngrok; no VPS IP, ACME email, new DNS/domain, paid ngrok endpoint,
firewall/SSH change, or modification/restart of ngrok/FastMCP/Hysteria is made.
The bundled Caddy is isolated from any existing system Caddy installation.

Headscale uses the official public DERP map; embedded DERP and DNS management are
disabled. One personal user may manually enroll at most 3 clients; the own-node
policy is not a registration quota. No clients/users/keys are created, no backup
is made, and existing Headscale/ingress state is never overwritten or wiped.

Special Tailscale POST Upgrade through ngrok remains UNVERIFIED. Local services
being active or HTTP responses do not prove end-to-end acceptance. The ngrok
switch command is printed for later manual review and is never executed here.
USAGE
}

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

if (($# == 0)); then
    usage
    exit 0
fi
(($# == 1)) || die 'Supply exactly one mode: --check, --install, or --help.'
case "$1" in
    --help|-h) usage; exit 0 ;;
    --check|--install) mode="$1" ;;
    *) die 'Unknown mode. Use --help.' ;;
esac

domain="${HEADSCALE_HOSTNAME:-}"
dns_base_domain="tail.${domain}"
headscale_version='0.29.6'
caddy_version='2.11.7'
workdir=''
phase='preflight'

cleanup() {
    if [[ -n "$workdir" ]]; then
        # Only fixed files created by this invocation; never recursively delete.
        rm -f -- "$workdir/headscale.deb" "$workdir/caddy.tar.gz" "$workdir/caddy" \
            "$workdir/config.yaml" "$workdir/policy.hujson" "$workdir/Caddyfile" \
            "$workdir/headscale-ingress.service"
        rmdir -- "$workdir"
    fi
}
trap cleanup EXIT
trap 'printf "ERROR: Failed during %s (line %s); no rollback or state deletion was attempted.\n" "$phase" "$LINENO" >&2' ERR

validate_hostname() {
    local value="$1" label
    [[ ${#value} -le 253 && "$value" == *.* && "$value" != *..* ]] || return 1
    [[ "$value" =~ ^[a-z0-9][a-z0-9.-]*[a-z]$ ]] || return 1
    case "$value" in
        example.com|*.example.com|example.net|*.example.net|example.org|*.example.org|*.example|*.invalid|*.test|*.localhost|*.local)
            return 1 ;;
    esac
    local IFS='.'
    for label in $value; do
        [[ ${#label} -ge 1 && ${#label} -le 63 ]] || return 1
        [[ "$label" != -* && "$label" != *- ]] || return 1
    done
}

[[ -n "$domain" ]] || die 'Set HEADSCALE_HOSTNAME to the existing ngrok bare hostname.'
validate_hostname "$domain" || die 'Use the existing lowercase bare hostname, not an example, URL, port, or path.'
validate_hostname "$dns_base_domain" || die 'Hostname is too long for the derived internal DNS base domain.'
# The derived child domain cannot be the server hostname or its suffix parent,
# satisfying v0.29.6 even while all client DNS management is disabled.

[[ "$(uname -s)" == 'Linux' ]] || die 'This script targets Linux only.'
((EUID == 0)) || die 'Run --check/--install as root to inspect protected paths reliably.'
for command in awk dpkg dpkg-query ss systemctl curl sha256sum mktemp rm rmdir install runuser tar; do
    command -v "$command" >/dev/null || die "Required existing command is missing: $command"
done
[[ -s /etc/ssl/certs/ca-certificates.crt ]] || die 'A working system CA bundle is required for the official HTTPS downloads.'
[[ -r /etc/os-release && -d /run/systemd/system ]] || die 'A supported systemd Linux host is required.'
os_id="$(awk -F= '$1 == "ID" {gsub(/"/, "", $2); print $2}' /etc/os-release)"
os_version="$(awk -F= '$1 == "VERSION_ID" {gsub(/"/, "", $2); print $2}' /etc/os-release)"
[[ "$os_version" =~ ^[0-9]+(\.[0-9]+)*$ ]] || die 'Cannot determine a numeric OS version.'
case "$os_id" in
    debian) dpkg --compare-versions "$os_version" ge 12 || die 'Debian >=12 is required.' ;;
    ubuntu) dpkg --compare-versions "$os_version" ge 22.04 || die 'Ubuntu >=22.04 is required.' ;;
    *) die 'Only Debian >=12 and Ubuntu >=22.04 are supported by this script.' ;;
esac
arch="$(dpkg --print-architecture)"
case "$arch" in
    amd64)
        headscale_sha256='a3b49916a16418c704cef89818d734bc8af0528aac965a2dd5ca4bfa4cef48e2'
        caddy_sha256='727b91701a392de6ebc5027509f548bf39979e5216340d0faed8fa5e69c84f8b'
        ;;
    arm64)
        headscale_sha256='077467b12ba2122086db434335fadfa8deee4dbddacb1f959eecc6d7d10b81d4'
        caddy_sha256='d8fc6d179a5d283028a472a5618564f6ad8a86fed513e64f032b3b0b7cc45e42'
        ;;
    *) die 'Only amd64 and arm64 are supported.' ;;
esac

# Refuse even empty directories and dangling symlinks: no prior state is erased.
for path in /etc/headscale /var/lib/headscale /run/headscale \
    /usr/bin/headscale /usr/local/bin/headscale \
    /etc/systemd/system/headscale.service /etc/systemd/system/headscale.service.d \
    /run/systemd/system/headscale.service /run/systemd/system/headscale.service.d \
    /lib/systemd/system/headscale.service /usr/lib/systemd/system/headscale.service \
    /etc/headscale-ingress /usr/local/lib/headscale-ingress \
    /etc/systemd/system/headscale-ingress.service /etc/systemd/system/headscale-ingress.service.d \
    /run/systemd/system/headscale-ingress.service /run/systemd/system/headscale-ingress.service.d \
    /lib/systemd/system/headscale-ingress.service /usr/lib/systemd/system/headscale-ingress.service; do
    [[ ! -e "$path" && ! -L "$path" ]] || die 'Existing Headscale or dedicated ingress state found; overwrite refused.'
done
if command -v headscale >/dev/null 2>&1; then
    die 'An existing Headscale executable was found; fresh state required.'
fi
if dpkg-query -W -f='${db:Status-Abbrev}' headscale >/dev/null 2>&1; then
    die 'Headscale has a package record; resolve prior state separately, not with this script.'
else
    query_status=$?
    ((query_status == 1)) || die 'Could not inspect the package database; preflight stopped.'
fi
for tcp_port in 18080 19080 50443; do
    listeners="$(ss -H -ltn "sport = :${tcp_port}")"
    [[ -z "$listeners" ]] || die "TCP/$tcp_port is already in use; no existing service was stopped."
done
if ! mcp_status="$(curl --silent --show-error --noproxy '*' \
    --max-time 10 --output /dev/null --write-out '%{http_code}' \
    --header "Host: ${domain}" --header 'Accept: application/json, text/event-stream' \
    http://127.0.0.1:8765/mcp)"; then
    die 'Local FastMCP probe failed; no service was changed.'
fi
[[ "$mcp_status" == '401' ]] || die 'Existing FastMCP must return HTTP 401 without credentials and with its original Host header.'
printf 'Preflight passed: fresh state; local TCP/18080, 19080 and 50443 are unused; FastMCP authentication gate returned 401.\n'
printf 'No public endpoint or token was accessed. HTTP 401 is not complete MCP acceptance.\n'
if [[ "$mode" == '--check' ]]; then
    printf 'Read-only check finished; no files, downloads, packages, services, tunnels, or firewall rules were changed.\n'
    exit 0
fi

phase='download and verify both pinned releases'
workdir="$(mktemp -d /tmp/headscale-rebuild.XXXXXXXX)"
headscale_url="https://github.com/juanfont/headscale/releases/download/v${headscale_version}/headscale_${headscale_version}_linux_${arch}.deb"
caddy_url="https://github.com/caddyserver/caddy/releases/download/v${caddy_version}/caddy_${caddy_version}_linux_${arch}.tar.gz"
curl --fail --show-error --silent --location --proto '=https' --proto-redir '=https' \
    --connect-timeout 15 --max-time 300 --tlsv1.2 --output "$workdir/headscale.deb" "$headscale_url"
printf '%s  %s\n' "$headscale_sha256" "$workdir/headscale.deb" | sha256sum --check --status
curl --fail --show-error --silent --location --proto '=https' --proto-redir '=https' \
    --connect-timeout 15 --max-time 300 --tlsv1.2 --output "$workdir/caddy.tar.gz" "$caddy_url"
printf '%s  %s\n' "$caddy_sha256" "$workdir/caddy.tar.gz" | sha256sum --check --status
tar --extract --gzip --file "$workdir/caddy.tar.gz" --directory "$workdir" \
    --no-same-owner --no-same-permissions caddy
[[ -f "$workdir/caddy" && ! -L "$workdir/caddy" ]] || die 'Verified Caddy archive did not yield a regular caddy file.'

phase='install pinned Headscale package'
# Install only this verified DEB; do not upgrade the host or existing services.
# The official package may auto-start Headscale with its default configuration.
dpkg --install "$workdir/headscale.deb"
systemctl stop headscale

phase='write fresh local configuration and isolated ingress'
install -d -o root -g headscale -m 0750 /etc/headscale
install -d -o headscale -g headscale -m 0750 /var/lib/headscale
install -d -o root -g root -m 0755 /etc/headscale-ingress /usr/local/lib/headscale-ingress
install -o root -g root -m 0755 "$workdir/caddy" /usr/local/lib/headscale-ingress/caddy
cat > "$workdir/config.yaml" <<YAML
server_url: "https://${domain}"
listen_addr: "127.0.0.1:18080"
metrics_listen_addr: ""
grpc_listen_addr: "127.0.0.1:50443"
grpc_allow_insecure: false
trusted_proxies:
  - 127.0.0.1/32
noise:
  private_key_path: /var/lib/headscale/noise_private.key
prefixes:
  v4: 100.64.0.0/10
  v6: fd7a:115c:a1e0::/48
  allocation: sequential
derp:
  server:
    enabled: false
  urls:
    - https://controlplane.tailscale.com/derpmap/default
  paths: []
  auto_update_enabled: true
  update_frequency: 3h
disable_check_updates: true
node:
  expiry: 0
  ephemeral:
    inactivity_timeout: 30m
database:
  type: sqlite
  debug: false
  sqlite:
    path: /var/lib/headscale/db.sqlite
    write_ahead_log: true
    wal_autocheckpoint: 1000
tls_letsencrypt_hostname: ""
tls_cert_path: ""
tls_key_path: ""
log:
  level: info
  format: text
policy:
  mode: file
  path: /etc/headscale/policy.hujson
dns:
  magic_dns: false
  base_domain: "${dns_base_domain}"
  override_local_dns: false
  nameservers:
    global: []
    split: {}
  search_domains: []
  extra_records: []
unix_socket: /var/run/headscale/headscale.sock
unix_socket_permission: "0770"
logtail:
  enabled: false
auto_update:
  enabled: false
YAML
cat > "$workdir/policy.hujson" <<'JSON'
{
  "grants": [
    {"src": ["autogroup:member"], "dst": ["autogroup:self"], "ip": ["*"]}
  ]
}
JSON
cat > "$workdir/Caddyfile" <<CADDYFILE
{
    admin off
    persist_config off
    auto_https off
}

http://:19080 {
    bind 127.0.0.1
    route {
        # Exact callback wins for every method, before Headscale's /auth/*.
        @mcp_callback path /auth/callback
        reverse_proxy @mcp_callback 127.0.0.1:8765 {
            header_up Host ${domain}
            header_up X-Forwarded-Proto https
        }

        @headscale_get {
            method GET
            path /key /ts2021 /health /version /register/* /auth/* /apple /apple/* /windows
        }
        reverse_proxy @headscale_get 127.0.0.1:18080 {
            header_up Host ${domain}
            header_up X-Real-IP {remote_host}
            header_up X-Forwarded-Proto https
        }

        @headscale_post {
            method POST
            path /ts2021
        }
        reverse_proxy @headscale_post 127.0.0.1:18080 {
            header_up Host ${domain}
            header_up X-Real-IP {remote_host}
            header_up X-Forwarded-Proto https
        }

        @headscale_head {
            method HEAD
            path /machine/ping-response
        }
        reverse_proxy @headscale_head 127.0.0.1:18080 {
            header_up Host ${domain}
            header_up X-Real-IP {remote_host}
            header_up X-Forwarded-Proto https
        }

        # Includes /mcp, /authorize, /token, exact /register, /revoke,
        # /consent and /.well-known/*; no prefix stripping or rewriting.
        reverse_proxy 127.0.0.1:8765 {
            header_up Host ${domain}
            header_up X-Forwarded-Proto https
        }
    }
}
CADDYFILE
cat > "$workdir/headscale-ingress.service" <<'UNIT'
[Unit]
Description=Dedicated local Headscale and FastMCP ingress
After=network.target

[Service]
Type=simple
DynamicUser=yes
ExecStart=/usr/local/lib/headscale-ingress/caddy run --config /etc/headscale-ingress/Caddyfile --adapter caddyfile
Restart=on-failure
RestartSec=5s
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
UMask=0077

[Install]
WantedBy=multi-user.target
UNIT
install -o root -g headscale -m 0640 "$workdir/config.yaml" /etc/headscale/config.yaml
install -o root -g headscale -m 0640 "$workdir/policy.hujson" /etc/headscale/policy.hujson
install -o root -g root -m 0644 "$workdir/Caddyfile" /etc/headscale-ingress/Caddyfile
install -o root -g root -m 0644 "$workdir/headscale-ingress.service" /etc/systemd/system/headscale-ingress.service

phase='validate new configuration only'
# configtest initializes keys/database, so use the service user while stopped.
runuser -u headscale -- headscale --config /etc/headscale/config.yaml configtest
/usr/local/lib/headscale-ingress/caddy validate --config /etc/headscale-ingress/Caddyfile --adapter caddyfile
phase='start only the two new services'
systemctl daemon-reload
systemctl enable --now headscale headscale-ingress
systemctl is-active --quiet headscale
systemctl is-active --quiet headscale-ingress

printf '\nNew local Headscale and ingress services started. Public POST Upgrade and end-to-end access remain UNVERIFIED.\n'
printf 'Existing ngrok, FastMCP and Hysteria were not stopped, restarted or reconfigured.\n'
printf 'Later MANUAL switch, after reviewing the existing tunnel process owner and rollback command:\n'
printf '  ngrok http http://127.0.0.1:19080 --url "https://%s" --inspect=false\n' "$domain"
printf 'Do not run a competing tunnel for the same free domain; coordinate the old tunnel switch manually.\n'
printf 'The command above was printed only and was NOT executed. Validate both Headscale and existing MCP flows afterward.\n'
printf 'No backup exists; a later fresh rebuild requires clients to register again.\n'
printf 'Manual enrollment (one personal user, at most 3 clients; replace <AUTH_ID>):\n'
printf '  sudo headscale users create owner\n'
printf '  tailscale up --login-server https://%s --accept-dns=false\n' "$domain"
printf '  sudo headscale auth register --user owner --auth-id "<AUTH_ID>"\n'
printf '  sudo headscale nodes list\n'
printf 'Run tailscale on each client, not on the Headscale VPS; enrollment needs the manual tunnel switch first.\n'
