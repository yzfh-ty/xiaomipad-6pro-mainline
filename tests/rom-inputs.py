#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""CI-only regression checks for pinned stock inputs; no tablet is accessed."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, PROJECT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


stock = load('stock', 'tools/lib/stock-rom.py')
trees = load('trees', 'tools/lib/verify-stock-dt.py')
installer = load('installer', 'tools/install-liuqin.py')
ci = load('ci', 'tools/prepare-ci-inputs.py')
lock = stock.table()
assert lock['rom'] == 'OS4.0.2.5.XMYCNXM'
assert lock['status'] == 'OFFLINE_INSPECTED'
assert lock['android_version'] == 17 and lock['anti_version'] == 1
assert lock['archive']['format'] == 'zip'
assert lock['archive']['members']['boot.img'] == 'boot_official.img'
assert lock['archive']['compression']['super.img'] == 'zstd'
assert not lock['images']['super.img']['sparse']
dt = json.loads((PROJECT / 'tools/lib/liuqin-stock-dt.json').read_text())
assert dt['rom'] == lock['rom'] and len(dt['base']) == 14 and len(dt['overlays']) == 44

with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    blob = b'one tree'
    (root / 'dtb-00.dtb').write_bytes(blob)
    expected = {'dtb-00.dtb': hashlib.sha256(blob).hexdigest()}
    trees.verify(root, expected, 'dtb-*.dtb')
    (root / 'dtb-00.dtb').write_bytes(b'other tree')
    try:
        trees.verify(root, expected, 'dtb-*.dtb')
    except ValueError:
        pass
    else:
        raise AssertionError('DT tampering was accepted')

    # Truncated vendor_boot must fail before any DT extraction.
    header = bytearray(4096)
    header[:8] = b'VNDRBOOT'
    struct.pack_into('<II', header, 8, 4, 4096)
    struct.pack_into('<II', header, 2096, 2128, 1024)
    (root / 'vendor_boot.img').write_bytes(header)
    try:
        stock.split_device_trees(root, root / 'analysis')
    except ValueError:
        pass
    else:
        raise AssertionError('Truncated vendor_boot was accepted')

    # Installer anti checks run after the image identity checks and before
    # touching any device. Small fixtures keep this independent of a real ROM.
    rom = root / 'rom'
    rom.mkdir()
    (rom / 'boot.img').write_bytes(b'fixture')
    table = {'rom': 'fixture', 'status': 'OFFLINE_INSPECTED', 'anti_version': 1,
             'images': {'boot.img': {'partition': 'boot_a', 'bytes': 7,
                                    'sha256': hashlib.sha256(b'fixture').hexdigest()}}}
    parser, _ = installer.parse_arguments(['--bundle', str(root)])
    with patch.object(installer, 'load_rom_table', return_value=table):
        try:
            installer.verify_rom(parser, rom)
        except SystemExit:
            pass
        else:
            raise AssertionError('Missing anti_version.txt was accepted')
        (rom / 'anti_version.txt').write_text('1\n')
        installer.verify_rom(parser, rom)
        (rom / 'boot.img').write_bytes(b'changed')
        try:
            installer.verify_rom(parser, rom)
        except SystemExit:
            pass
        else:
            raise AssertionError('Wrong ROM payload was accepted')

    with patch.object(ci, 'run', side_effect=AssertionError('Downloader must not run')):
        for url in ('http://example.org/rom.tgz', 'https://name:password@example.org/rom.tgz'):
            try:
                ci.download(url, root / 'never-created', '0' * 64)
            except ValueError:
                pass
            else:
                raise AssertionError('Unacceptable download URL')

print('PASS: OS4 identities, DT tampering/truncation, anti checks and download URL policy')
