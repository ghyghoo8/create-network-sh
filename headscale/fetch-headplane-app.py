#!/usr/bin/env python3
"""Fetch Headplane 0.8.2's pinned application into a NEW native app directory.

This is a custom native delivery of unmodified application files from the
official ghcr.io/tale/headplane image, not an official native release archive.
No Docker, compilation, service action, or private configuration is involved.

Sources (verified for v0.8.2):
https://github.com/tale/headplane/blob/v0.8.2/Dockerfile
https://github.com/tale/headplane/blob/v0.8.2/vite.config.ts
https://headplane.net/install/native-mode

linux/amd64 manifest:
sha256:df325c86556b9485104931fad476364922a765f865a4a00e9af847ce45b0f04a
Only the two COPY layers below are needed for the bundled Node application.
The optional agent is not included. Run with the separately verified Node
24.22.1 runtime, from the app directory: node build/server/index.js.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tarfile
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


LAYERS = (
    ("build", "0a62fd590d4ff0459926f367aa7c5f72550234e99a8abd1e0a1d22e22b1b2545", 22674810),
    ("drizzle", "35c4d8d6af473c41eb9f86daafcd4444166436ce8de27adfbd6daa5c2c259f74", 2884),
)
MAX_UNPACKED_BYTES = 256 * 1024 * 1024


class PublicArtifactRedirects(HTTPRedirectHandler):
    """Do not forward the anonymous registry token to a blob storage host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urlsplit(newurl).scheme != "https":
            raise ValueError("artifact redirect must remain HTTPS")
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is not None and urlsplit(newurl).netloc != "ghcr.io":
            redirected.remove_header("Authorization")
        return redirected


def extract_layer(archive, app, directory):
    """Extract regular files under one approved COPY prefix, never tar owners."""
    prefix = f"app/{directory}"
    total = 0
    files = 0
    with tarfile.open(archive, "r:gz") as source:
        for member in source:
            name = member.name.rstrip("/")
            parts = name.split("/")
            if (
                name.startswith("/") or "\\" in name
                or any(part in ("", ".", "..") or part.startswith(".wh.") for part in parts)
            ):
                raise ValueError("unsafe archive path")
            if name == "app" and member.isdir():
                continue
            if name != prefix and not name.startswith(prefix + "/"):
                raise ValueError("archive contains a path outside its approved COPY directory")
            if not member.isdir() and not member.isfile():
                raise ValueError("archive links and special files are not allowed")
            target = app.joinpath(*parts[1:])
            if member.isdir():
                target.mkdir(mode=0o755, parents=True, exist_ok=True)
                continue
            total += member.size
            files += 1
            if member.size < 0 or total > MAX_UNPACKED_BYTES or files > 20000:
                raise ValueError("archive exceeds the application extraction limit")
            target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
            with source.extractfile(member) as incoming, target.open("xb") as outgoing:
                shutil.copyfileobj(incoming, outgoing, length=1024 * 1024)
            target.chmod(0o644)
    if files == 0:
        raise ValueError("application layer contains no files")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--destination", required=True, help="new app directory; its parent must already exist")
    args = parser.parse_args()
    destination = Path(os.path.abspath(args.destination))
    parent = destination.parent
    if parent.resolve(strict=True) != parent:
        raise ValueError("destination parent must not contain symlinks")
    info = parent.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o022:
        raise ValueError("destination parent must be owned by the current account and not group/world writable")
    if os.path.lexists(destination):
        raise ValueError("destination already exists; nothing was overwritten")

    opener = build_opener(PublicArtifactRedirects())
    token_request = Request("https://ghcr.io/token?service=ghcr.io&scope=repository:tale/headplane:pull")
    with opener.open(token_request, timeout=30) as response:
        token_body = response.read(65537)
    if len(token_body) > 65536:
        raise ValueError("unexpected registry token response size")
    token = json.loads(token_body).get("token")
    if not isinstance(token, str) or not token or "\n" in token or "\r" in token:
        raise ValueError("unexpected anonymous registry token")

    with tempfile.TemporaryDirectory(prefix=".headplane-stage-", dir=parent) as temporary:
        stage = Path(temporary)
        app = stage / "app"
        app.mkdir(mode=0o755)
        for index, (directory, digest, size) in enumerate(LAYERS, 1):
            print(f"Downloading application layer {index}/{len(LAYERS)} ({directory}); no retries.", flush=True)
            request = Request(
                f"https://ghcr.io/v2/tale/headplane/blobs/sha256:{digest}",
                headers={"Authorization": f"Bearer {token}"},
            )
            archive = stage / f"{directory}.tar.gz"
            checksum = hashlib.sha256()
            downloaded = 0
            deadline = time.monotonic() + 300
            with opener.open(request, timeout=30) as response, archive.open("xb") as output:
                while True:
                    if time.monotonic() > deadline:
                        raise TimeoutError("application layer download exceeded 300 seconds")
                    chunk = response.read(64 * 1024)
                    if not chunk:
                        break
                    downloaded += len(chunk)
                    if downloaded > size:
                        raise ValueError("application layer exceeds its pinned size")
                    checksum.update(chunk)
                    output.write(chunk)
            if downloaded != size or checksum.hexdigest() != digest:
                raise ValueError("application layer size or SHA-256 does not match the pinned release")
            extract_layer(archive, app, directory)
            archive.unlink()
            print(f"Verified and extracted {directory}.", flush=True)

        if not (app / "build/server/index.js").is_file() or not (app / "drizzle").is_dir():
            raise ValueError("verified layers do not contain the expected native application")
        # The installer may use umask 027 as root. Explicitly make only this
        # new application's directories traversable by its service account.
        # Ordinary files were already normalized to 0644 during extraction.
        app.chmod(0o755)
        for entry in app.rglob("*"):
            if entry.is_dir():
                entry.chmod(0o755)
        if os.path.lexists(destination):
            raise ValueError("destination appeared during preparation; nothing was overwritten")
        os.rename(app, destination)
    print(f"Headplane 0.8.2 application prepared at {destination}; no application or service was executed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except HTTPError as error:
        print(f"ERROR: official artifact request returned HTTP {error.code}; no service changed.", file=sys.stderr)
        raise SystemExit(1)
    except URLError as error:
        print(f"ERROR: official artifact connection failed ({error.reason}); no service changed.", file=sys.stderr)
        raise SystemExit(1)
    except (OSError, ValueError, tarfile.TarError) as error:
        print(f"ERROR: {error}; no service changed.", file=sys.stderr)
        raise SystemExit(1)
