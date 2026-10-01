#!/usr/bin/env python3
"""Build or check the release zip of the skill folder.

The archive is reproducible: entries are sorted, timestamps and modes are fixed
and only files git tracks are included, so an unchanged skill yields identical
bytes.
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT/'cloud-architecture-drawio'
TARGET = ROOT/'dist/cloud-architecture-drawio.zip'
SKIP_PARTS = {'__pycache__', 'node_modules'}


def skill_files():
    """Files git tracks in the skill folder, so ignored files such as .env never ship."""
    try:
        listed = subprocess.run(['git', 'ls-files', '-z', '--', SKILL.name], cwd=ROOT, capture_output=True, check=True).stdout
        files = [ROOT/name for name in listed.decode('utf-8').split('\0') if name]
    except (OSError, subprocess.CalledProcessError):
        # Outside a git checkout, skip caches and every dotfile instead.
        files = [path for path in SKILL.rglob('*')
                 if not set(path.relative_to(SKILL).parts) & SKIP_PARTS
                 and not any(part.startswith('.') for part in path.relative_to(SKILL).parts)
                 and path.suffix != '.pyc']
    return sorted(path for path in files if path.is_file())


def build(target=TARGET):
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name+'.tmp')
    with zipfile.ZipFile(tmp, 'w') as archive:
        for path in skill_files():
            info = zipfile.ZipInfo(path.relative_to(ROOT).as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes(), compresslevel=9)
    os.replace(tmp, target)
    return target


def differences(target=TARGET):
    """Describe how the archive differs from the skill folder; empty when in sync."""
    if not target.exists():
        return [f'{target.relative_to(ROOT)} is missing']
    expected = {path.relative_to(ROOT).as_posix(): path.read_bytes() for path in skill_files()}
    with zipfile.ZipFile(target) as archive:
        actual = {name: archive.read(name) for name in archive.namelist()}
    problems = [f'missing from zip: {name}' for name in sorted(expected.keys()-actual.keys())]
    problems += [f'not in skill folder: {name}' for name in sorted(actual.keys()-expected.keys())]
    problems += [f'stale in zip: {name}' for name in sorted(expected.keys() & actual.keys()) if expected[name] != actual[name]]
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='report differences instead of building')
    args = parser.parse_args()
    if args.check:
        problems = differences()
        print('\n'.join(problems) or 'release zip matches the skill folder')
        sys.exit(1 if problems else 0)
    print(build().relative_to(ROOT))


if __name__ == '__main__':
    main()
