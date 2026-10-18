#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Normalize checksum-pinned ROM inputs without executing vendor scripts."""
import hashlib
import json
from pathlib import Path
import stat
import struct
import tarfile
import zipfile

PROJECT = Path(__file__).resolve().parents[2]


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def table():
    # The same helper is shipped next to the manifest in an installation bundle.
    sibling = Path(__file__).with_name('liuqin-rom-images.json')
    path = sibling if sibling.is_file() else PROJECT / 'tools/lib/liuqin-rom-images.json'
    return json.loads(path.read_text())


def verify_images(images, lock=None):
    lock = table() if lock is None else lock
    for name, entry in lock['images'].items():
        path = images / name
        if (path.is_symlink() or not path.is_file() or
                path.stat().st_size != entry['bytes'] or sha(path) != entry['sha256']):
            raise ValueError(f"Wrong {lock['rom']} input: {path}")
    if (images / 'anti_version.txt').read_text().strip() != str(lock['anti_version']):
        raise ValueError('ROM anti_version.txt differs from the pinned package')


def copy_bounded(incoming, output, expected):
    """Stop a malformed compressed member before it can exceed its pinned size."""
    total = 0
    while chunk := incoming.read(min(1 << 20, expected - total + 1)):
        total += len(chunk)
        if total > expected:
            raise ValueError('ROM member exceeds its pinned uncompressed size')
        output.write(chunk)
    if total != expected:
        raise ValueError('Truncated ROM member')


def unpack_rom(archive, images, lock=None):
    """Extract only reviewed payloads and normalize their installer filenames.

    No boot_magisk, Magisk executables, FRP, userdata, GPT or flashing scripts
    are extracted. Archive identity and every resulting image remain pinned.
    """
    lock = table() if lock is None else lock
    identity = lock['archive']
    if archive.stat().st_size != identity['bytes'] or sha(archive) != identity['sha256']:
        raise ValueError('ROM archive identity mismatch')
    for name in lock['images']:
        if not name or Path(name).name != name or '/' in name or '\\' in name:
            raise ValueError('Unsafe normalized image name')
    if images.exists():
        raise ValueError('Output images directory exists; use a new output directory')
    fmt = identity.get('format', 'tgz')
    if fmt not in ('zip', 'tgz'):
        raise ValueError('Unsupported ROM archive format')
    images.mkdir(parents=True)
    if fmt == 'zip':
        members = identity['members']
        if set(members) != set(lock['images']) or len(set(members.values())) != len(members):
            raise ValueError('ROM archive mapping must cover every pinned image exactly once')
        compression = identity.get('compression', {})
        if not set(compression) <= set(members) or set(compression.values()) - {'zstd'}:
            raise ValueError('Unsupported ROM member compression')
        with zipfile.ZipFile(archive) as source:
            entries = source.infolist()
            for name, member in members.items():
                matches = [item for item in entries if item.filename == member]
                if (len(matches) != 1 or matches[0].is_dir() or
                        stat.S_ISLNK(matches[0].external_attr >> 16)):
                    raise ValueError('Missing, duplicate or nonregular ROM member: ' + member)
                expected = lock['images'][name]['bytes']
                if name not in compression and matches[0].file_size != expected:
                    raise ValueError('Unexpected ROM member size: ' + member)
                with source.open(matches[0]) as incoming, (images / name).open('xb') as output:
                    if compression.get(name) == 'zstd':
                        import zstandard
                        with zstandard.ZstdDecompressor().stream_reader(incoming, closefd=False) as reader:
                            copy_bounded(reader, output, expected)
                    else:
                        copy_bounded(incoming, output, expected)
        # This port has no anti_version.txt. Its protected base firmware was
        # compared with the pinned OS3 anti=1 baseline before admitting it.
        # The explicit provenance entry prevents treating an absent value as 0.
        if lock.get('anti_version_source') != 'verified-os3-base-firmware':
            raise ValueError('ZIP ROM lacks a reviewed anti-version provenance')
        (images / 'anti_version.txt').write_text(str(lock['anti_version']) + '\n')
    else:
        wanted = set(lock['images']) | {'anti_version.txt'}
        seen = set()
        with tarfile.open(archive, 'r|gz') as source:
            for entry in source:
                parts = entry.name.split('/')
                if len(parts) < 2 or parts[-2] != 'images' or parts[-1] not in wanted:
                    continue
                if not entry.isfile() or entry.name.startswith('/') or '..' in parts or parts[-1] in seen:
                    raise ValueError('Unexpected stock ROM archive member')
                name = parts[-1]
                if name == 'anti_version.txt' and entry.size > 32:
                    raise ValueError('Unexpected anti-version file size')
                expected = entry.size if name == 'anti_version.txt' else lock['images'][name]['bytes']
                with source.extractfile(entry) as incoming, (images / name).open('xb') as output:
                    copy_bounded(incoming, output, expected)
                seen.add(name)
        if seen != wanted:
            raise ValueError(f'Incomplete ROM archive: {wanted - seen}')
    verify_images(images, lock)
    return images


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
