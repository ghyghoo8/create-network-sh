#!/usr/bin/env python3
"""Patch or restore reviewed G8 lifecycle scripts without replacing private settings.

Run as the existing gateway owner, with no concurrent start/stop invocation.
This helper neither sources the scripts nor starts or stops any service.
"""

import argparse
import hashlib
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from contextlib import ExitStack


# Ignore the private NGROK_URL line and normalize final LF-only padding when
# fingerprinting. All other bytes must match the reviewed lifecycle version.
# Actual patch/revert operations preserve the original final padding.
START_SHA256 = "70856a051133918021f352d0fe40c4de0677cd48835a86e8a96aaa913c21b93c"
STOP_SHA256 = "1021cb0d304693342a58a4b3316394b2f79eb1d6a5519effe277649e406ebae3"
NGROK_URL_LINE = re.compile(
    rb'(?m)^NGROK_URL="https://[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?'
    rb'(?::[0-9]{1,5})?"(?:[ \t]+#[^\r\n]*)?[ \t]*$'
)
START_OLD = (
    b'    launch_service ngrok "$NGROK_BIN" http "http://127.0.0.1:$GATEWAY_PORT" \\\n'
)
START_NEW = (
    b'    launch_service ngrok "$NGROK_BIN" http "http://127.0.0.1:19080" \\\n'
)
STOP_ARGUMENT_ANCHOR = b"umask 077\n\n"
STOP_ARGUMENTS = b'''# BEGIN shared-ngrok arguments (headscale helper)
STOP_NGROK_ONLY=0
if (($# == 1)); then
    case "$1" in
        --ngrok-only) STOP_NGROK_ONLY=1 ;;
        --help|-h)
            printf '%s\\n' 'Usage: bash stop.sh [--ngrok-only]' \\
                'No arguments: stop managed ngrok and gateway.' \\
                '--ngrok-only: stop managed ngrok; leave gateway untouched.'
            exit 0 ;;
        *) printf '%s\\n' 'Unknown argument. Use --help.' >&2; exit 2 ;;
    esac
elif (($# != 0)); then
    printf '%s\\n' 'Supply no arguments, --ngrok-only, or --help.' >&2
    exit 2
fi
# END shared-ngrok arguments (headscale helper)

'''
STOP_OLD = b'''event STOP_REQUEST control "directory=$GATEWAY_DIR"
STOP_FAILED=0
# Stop public forwarding first, then the gateway. Never use global pkill.
stop_service ngrok requested || STOP_FAILED=1
stop_service gateway requested || STOP_FAILED=1
if (( STOP_FAILED != 0 )); then
    event STOP_INCOMPLETE control 'Some process metadata could not be verified or stopped.'
    exit 1
fi
event STOP_COMPLETE control 'Managed services stopped; logs retained.'
printf '\\nManaged services stopped. Logs retained at %s\\n' "$LOG_DIR"
'''
STOP_NEW = b'''event STOP_REQUEST control "directory=$GATEWAY_DIR"
STOP_FAILED=0
# Keep the existing verified stop_service implementation and private groups.
stop_service ngrok requested || STOP_FAILED=1
if (( STOP_NGROK_ONLY == 0 )); then
    stop_service gateway requested || STOP_FAILED=1
fi
if (( STOP_FAILED != 0 )); then
    event STOP_INCOMPLETE control 'Some process metadata could not be verified or stopped.'
    exit 1
fi
if (( STOP_NGROK_ONLY != 0 )); then
    event STOP_COMPLETE control 'Managed ngrok stop complete; gateway untouched; logs retained.'
    printf '\\nManaged ngrok stop complete. Gateway untouched. Logs retained at %s\\n' "$LOG_DIR"
else
    event STOP_COMPLETE control 'Managed services stopped; logs retained.'
    printf '\\nManaged services stopped. Logs retained at %s\\n' "$LOG_DIR"
fi
'''


def script_fingerprint(content):
    return hashlib.sha256(content.rstrip(b"\n") + b"\n").hexdigest()


def patched_start(content):
    old_count, new_count = content.count(START_OLD), content.count(START_NEW)
    if (old_count, new_count) not in ((1, 0), (0, 1)):
        raise ValueError("start.sh has an unknown ngrok launch structure")
    original = content.replace(START_NEW, START_OLD, 1) if new_count else content
    normalized, url_count = NGROK_URL_LINE.subn(
        b'NGROK_URL="<preserved-url>"', original
    )
    if url_count != 1 or script_fingerprint(normalized) != START_SHA256:
        raise ValueError("start.sh differs from the reviewed lifecycle version")
    return original.replace(START_OLD, START_NEW, 1)


def patched_stop(content):
    if content.count(STOP_ARGUMENTS) == 1 and content.count(STOP_NEW) == 1:
        original = content.replace(STOP_ARGUMENTS, b"", 1).replace(
            STOP_NEW, STOP_OLD, 1
        )
    elif (
        b"# BEGIN shared-ngrok arguments" not in content
        and content.count(STOP_OLD) == 1
    ):
        original = content
    else:
        raise ValueError("stop.sh has an unknown argument or stop structure")
    if script_fingerprint(original) != STOP_SHA256:
        raise ValueError("stop.sh differs from the reviewed lifecycle version")
    if original.count(STOP_ARGUMENT_ANCHOR) != 1:
        raise ValueError("stop.sh has an unknown initialization structure")
    return original.replace(
        STOP_ARGUMENT_ANCHOR, STOP_ARGUMENT_ANCHOR + STOP_ARGUMENTS, 1
    ).replace(STOP_OLD, STOP_NEW, 1)


def file_version(info):
    return (
        info.st_dev, info.st_ino, info.st_uid, info.st_mode,
        info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_nlink,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--gateway-dir", required=True,
        help="existing gateway directory, owned by the current service account",
    )
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--check", action="store_true", help="validate only; no writes")
    modes.add_argument("--apply", action="store_true", help="patch only start.sh and stop.sh")
    modes.add_argument("--revert", action="store_true", help="restore the reviewed original scripts")
    args = parser.parse_args()
    gateway = Path(os.path.abspath(args.gateway_dir))
    uid = os.geteuid()

    if gateway.resolve(strict=True) != gateway:
        raise ValueError("gateway directory path must not contain symlinks")
    directory_info = gateway.lstat()
    if not stat.S_ISDIR(directory_info.st_mode) or directory_info.st_uid != uid:
        raise ValueError("use the account that owns the gateway directory; do not switch users")

    with ExitStack() as stack:
        directory_fd = os.open(gateway, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        stack.callback(os.close, directory_fd)
        opened_directory = os.fstat(directory_fd)
        if (
            opened_directory.st_dev != directory_info.st_dev
            or opened_directory.st_ino != directory_info.st_ino
            or opened_directory.st_uid != uid
        ):
            raise ValueError("gateway directory changed during validation")

        records = []
        for name, patch in (("start.sh", patched_start), ("stop.sh", patched_stop)):
            flags = os.O_RDWR if args.apply or args.revert else os.O_RDONLY
            fd = os.open(name, flags | os.O_NOFOLLOW, dir_fd=directory_fd)
            stack.callback(os.close, fd)
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != uid or info.st_nlink != 1:
                raise ValueError(f"{name} must be a regular script owned by the current account, without extra hard links")
            # No temporary or backup copy: keep the existing content in memory.
            with os.fdopen(os.dup(fd), "rb") as source:
                content = source.read()
            content.decode("utf-8")
            updated = patch(content)
            if args.revert:
                if name == "start.sh":
                    updated = updated.replace(START_NEW, START_OLD, 1)
                else:
                    updated = updated.replace(STOP_ARGUMENTS, b"", 1).replace(
                        STOP_NEW, STOP_OLD, 1
                    )
            syntax = subprocess.run(
                ["/bin/bash", "--noprofile", "--norc", "-n"],
                input=updated,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={"PATH": "/usr/bin:/bin", "LC_ALL": "C", "BASH_ENV": "/dev/null", "ENV": "/dev/null"},
                check=False,
            )
            if syntax.returncode:
                # Bash errors can contain source text; never print private settings.
                raise ValueError(f"{name}: Bash syntax validation failed; no files changed")
            records.append((name, fd, info, content, updated))

        # Validate both scripts before any write, including a concurrent-edit check.
        for name, fd, info, content, updated in records:
            current_path = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if file_version(os.fstat(fd)) != file_version(info) or file_version(current_path) != file_version(info):
                raise ValueError(f"{name} changed during validation; no files changed")

        if args.check:
            for name, fd, info, content, updated in records:
                status = "already configured" if content == updated else "patch required"
                print(f"CHECK {name}: {status}; syntax valid")
            print("Read-only check passed. No files or services changed.")
            return 0

        for name, fd, info, content, updated in records:
            if content == updated:
                state = "already restored" if args.revert else "already configured"
                print(f"UNCHANGED {name}: {state}")
                continue
            os.lseek(fd, 0, os.SEEK_SET)
            remaining = memoryview(updated)
            while remaining:
                written = os.write(fd, remaining)
                if written == 0:
                    raise OSError("short write while updating a script")
                remaining = remaining[written:]
            os.ftruncate(fd, len(updated))
            os.fsync(fd)
            action = "RESTORED" if args.revert else "UPDATED"
            print(f"{action} {name}")

    print("Local script configuration complete; no service was started or stopped.")
    print("The original ngrok URL, gateway port, credentials and script permissions were preserved.")
    if args.revert:
        print("Original ngrok upstream and stop behavior restored. Use the original owner account: bash start.sh.")
    else:
        print("When ready, use the original owner account: bash stop.sh --ngrok-only; then bash start.sh.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        print(f"ERROR: {error}. No services were started or stopped.", file=sys.stderr)
        raise SystemExit(1)
