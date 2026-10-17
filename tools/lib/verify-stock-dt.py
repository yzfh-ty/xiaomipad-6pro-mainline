#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Verify every stock base DTB/DTBO consumed by the Ubuntu boot builder."""
import argparse
import hashlib
import json
from pathlib import Path


def verify(directory, expected, pattern):
    files = {p.name: p for p in directory.glob(pattern) if p.is_file()}
    if set(files) != set(expected):
        raise ValueError(f'Stock DT file set differs: {directory}')
    for name, digest in expected.items():
        path = files[name]
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f'Stock DT identity differs: {path}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-dir', type=Path, required=True)
    parser.add_argument('--overlay-dir', type=Path, required=True)
    args = parser.parse_args()
    table = json.loads(Path(__file__).with_name('liuqin-stock-dt.json').read_text())
    verify(args.base_dir, table['base'], 'dtb-*.dtb')
    verify(args.overlay_dir, table['overlays'], 'entry.*')
    print(f"Stock device trees verified: {table['rom']}")


if __name__ == '__main__':
    main()
