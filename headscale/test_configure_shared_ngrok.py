"""Offline regression checks; never execute the gateway lifecycle scripts."""

import hashlib
from pathlib import Path
import runpy
import stat
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "headscale/configure-shared-ngrok.py"
MODULE = runpy.run_path(str(HELPER), run_name="regression")
BASE = ROOT / "fastmcp/gitee/完整部署/01_代码与脚本"
START = (BASE / "start.sh").read_bytes()
STOP = (BASE / "stop.sh").read_bytes()


class LifecycleFingerprintTests(unittest.TestCase):
    def test_reported_extra_final_newline(self):
        candidate = START + b"\n"
        normalized, count = MODULE["NGROK_URL_LINE"].subn(
            b'NGROK_URL="<preserved-url>"', candidate
        )
        self.assertEqual(count, 1)
        self.assertEqual(
            hashlib.sha256(normalized).hexdigest(),
            "02749f98bf6b2aa5efed5b67043f5f8d71aecc371be33eb2bdcf9cb932485efb",
        )
        self.assertEqual(
            MODULE["patched_start"](candidate),
            candidate.replace(MODULE["START_OLD"], MODULE["START_NEW"], 1),
        )

    def test_final_padding_does_not_relax_body_checks(self):
        for padding in (b"\n", b"\n\n\n", b"\n" * 10):
            with self.subTest(padding=len(padding)):
                MODULE["patched_start"](START + padding)
                MODULE["patched_stop"](STOP + padding)
                with self.assertRaises(ValueError):
                    MODULE["patched_start"](
                        START.replace(b"set -Eeuo pipefail\n", b"set -Eeuo pipefail\n\n", 1)
                        + padding
                    )

    def test_apply_revert_preserve_private_url_padding_and_mode(self):
        start, count = MODULE["NGROK_URL_LINE"].subn(
            b'NGROK_URL="https://test-gateway.ngrok-free.dev"', START
        )
        self.assertEqual(count, 1)
        start += b"\n"
        stop = STOP + b"\n\n"
        with tempfile.TemporaryDirectory(prefix="headscale-fingerprint-") as temp:
            directory = Path(temp).resolve()
            for name, content in (("start.sh", start), ("stop.sh", stop)):
                (directory / name).write_bytes(content)
                (directory / name).chmod(0o700)
            (directory / ".env").write_bytes(b"TEST_SENTINEL=unchanged\n")

            def run(mode):
                result = subprocess.run(
                    [sys.executable, "-B", str(HELPER), "--gateway-dir", str(directory), mode],
                    capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

            run("--check")
            self.assertEqual((directory / "start.sh").read_bytes(), start)
            self.assertEqual((directory / "stop.sh").read_bytes(), stop)
            for _ in range(2):
                run("--apply")
                patched = {name: (directory / name).read_bytes() for name in ("start.sh", "stop.sh")}
                run("--apply")
                for name, content in patched.items():
                    self.assertEqual((directory / name).read_bytes(), content)
                run("--revert")
                self.assertEqual((directory / "start.sh").read_bytes(), start)
                self.assertEqual((directory / "stop.sh").read_bytes(), stop)
            for name in ("start.sh", "stop.sh"):
                self.assertEqual(stat.S_IMODE((directory / name).stat().st_mode), 0o700)
            self.assertEqual((directory / ".env").read_bytes(), b"TEST_SENTINEL=unchanged\n")
            self.assertEqual({p.name for p in directory.iterdir()}, {"start.sh", "stop.sh", ".env"})


if __name__ == "__main__":
    unittest.main()
