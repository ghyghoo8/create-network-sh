"""Byte-exact manifest for the original eight files; no network or credentials."""
import hashlib
import json
import sys
from pathlib import Path

# Original Library byte snapshot checked 2026-10-08 07:39:37 UTC.
EXPECTED_SOURCE = {'诊断与对接/OpenAI最小技术反馈_2026-10-01.txt': {'bytes': 1707, 'sha256': '4571474d1ced6890588a1655f51ba945dfde8125144936175ba7a905d8deb0d5'}, '诊断与对接/Codex本地会话直连诊断_2026-10-01.docx': {'bytes': 39242, 'sha256': 'f3d60906ea89cd6d1e8c668f176892f62e0d85f31cd0c36c48d070d9987f7788'}, '05_研究协作请求响应.schema.json': {'bytes': 16260, 'sha256': 'e9f4af5bff2b54fa95852ff38937de452639450bf5ac8fc7378805bc5f4e2282'}, '资讯与催化/04_试运行配置与验收案例.json': {'bytes': 34576, 'sha256': 'ad4cc428ace4bc8fbaa6fb9a9501655dd67a60e013137acc61e3701c54ab4060'}, '资讯与催化/03_事件数据契约.schema.json': {'bytes': 34618, 'sha256': 'f47e6921eff87fcd530800c0f10e0e3e23fc9c7ec48ae16d8a979b9f84218cd3'}, '资讯与催化/02_资讯与催化技术方案.docx': {'bytes': 44834, 'sha256': '308c7fa0fd5dfae56010102825aeff248b4d926605dc8c307fc5f004fea5ab5e'}, '00_项目总览与阶段验收.docx': {'bytes': 40627, 'sha256': 'd4b0d21a71e2e83663b67fa62c2bba88dc55077560ec119bab7e61f23b00a1c9'}, '01_开发指引与协作约束.docx': {'bytes': 44913, 'sha256': '0be8740a40d9fd8557331d0d7ada7d24b40e4ac8221f7c8338dac5c1cf13bb89'}}


def inventory(root):
    root = Path(root).resolve(strict=True)
    result = {}
    for f in sorted(root.rglob('*')):
        rel = f.relative_to(root)
        if '.git' in rel.parts:
            continue
        if f.is_symlink():
            raise ValueError('Symlinks are not allowed')
        if f.is_file():
            if f.name in {'.env', 'token', '.token'} or f.suffix in {'.key', '.pem'}:
                raise ValueError('Credential-like filename found; stop and review')
            b = f.read_bytes()
            result[rel.as_posix()] = {'bytes': len(b), 'sha256': hashlib.sha256(b).hexdigest()}
    if len(result) != 8:
        raise ValueError('Expected exactly eight source files excluding .git')
    if result != EXPECTED_SOURCE:
        raise ValueError('Files differ from the verified 2026-10-08 source snapshot; stop and review')
    return result


def main():
    if len(sys.argv) != 4 or sys.argv[1] not in {'create', 'verify'}:
        raise ValueError('Usage: migration_manifest.py create|verify ROOT MANIFEST_JSON')
    mode, root, manifest = sys.argv[1:]
    data = inventory(root)
    target = Path(manifest).resolve()
    if target.is_relative_to(Path(root).resolve()):
        raise ValueError('Manifest must be outside the source/clone tree')
    if mode == 'create':
        with target.open('x', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print('PASS: saved eight-file source manifest')
    else:
        expected = json.loads(target.read_text())
        if data != expected:
            raise ValueError('Remote clone differs from source paths, byte counts or hashes')
        print('PASS: all eight file paths, byte counts and SHA-256 hashes match')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'FAIL: {exc}', file=sys.stderr)
        raise SystemExit(1)
