#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Read pinned stock inputs without executing Xiaomi's flashing scripts."""
import hashlib
import json
from pathlib import Path
import struct

PROJECT = Path(__file__).resolve().parents[2]


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def table():
    return json.loads((PROJECT / 'tools/lib/liuqin-rom-images.json').read_text())


def verify_images(images):
    lock = table()
    for name, entry in lock['images'].items():
        path = images / name
        if path.stat().st_size != entry['bytes'] or sha(path) != entry['sha256']:
            raise ValueError(f"Wrong {lock['rom']} input: {path}")
    if (images / 'anti_version.txt').read_text().strip() != str(lock['anti_version']):
        raise ValueError('ROM anti_version.txt differs from the pinned package')


def split_device_trees(images, destination):
    """Split v4 vendor_boot's concatenated FDTs and the Android DTBO table."""
    vendor = (images / 'vendor_boot.img').read_bytes()
    if vendor[:8] != b'VNDRBOOT' or struct.unpack_from('<I', vendor, 8)[0] != 4:
        raise ValueError('Expected a v4 stock vendor_boot image')
    page = struct.unpack_from('<I', vendor, 12)[0]
    if page != 4096:
        raise ValueError('Unexpected vendor_boot page size')
    ramdisk = struct.unpack_from('<I', vendor, 24)[0]
    header, size = struct.unpack_from('<II', vendor, 2096)
    align = lambda n: (n + page - 1) // page * page
    offset = align(header) + align(ramdisk)
    if offset + size > len(vendor):
        raise ValueError('Truncated vendor_boot DTB section')
    payload = vendor[offset:offset + size]
    base = destination / 'vendor_boot/dtbs'
    overlays = destination / 'dtbo'
    base.mkdir(parents=True, exist_ok=False)
    overlays.mkdir(parents=True, exist_ok=False)
    pos, index = 0, 0
    while pos < len(payload):
        if payload[pos:pos + 4] != b'\xd0\x0d\xfe\xed':
            raise ValueError('Invalid concatenated stock DTB')
        length = struct.unpack_from('>I', payload, pos + 4)[0]
        if length < 40 or pos + length > len(payload):
            raise ValueError('Truncated stock DTB')
        (base / f'dtb-{index:02d}.dtb').write_bytes(payload[pos:pos + length])
        pos += length
        index += 1
    data = (images / 'dtbo.img').read_bytes()
    magic, total, header, entry_size, count, entries, _, version = struct.unpack_from('>8I', data)
    if magic != 0xd7b7ab1e or header != 32 or entry_size != 32 or version != 0:
        raise ValueError('Unexpected stock DTBO table')
    if total > len(data) or entries + count * entry_size > total:
        raise ValueError('Truncated stock DTBO table')
    for i in range(count):
        length, offset = struct.unpack_from('>II', data, entries + i * entry_size)
        if offset < entries + count * entry_size or offset + length > total:
            raise ValueError('Invalid DTBO entry bounds')
        (overlays / f'entry.{i}').write_bytes(data[offset:offset + length])
    return base, overlays
