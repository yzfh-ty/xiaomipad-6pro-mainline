#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise ZIP/Zstd normalization and rejection paths without a ROM or device."""
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import stat
import tarfile
import tempfile
import unittest
import warnings
import zipfile

import zstandard

PROJECT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('stock', PROJECT / 'tools/lib/stock-rom.py')
stock = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stock)


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.payloads = {'boot.img': b'unpatched custom-kernel boot', 'super.img': b'raw super' * 1024}
        self.members = {'boot.img': 'boot_official.img', 'super.img': 'super.zst'}
        self.lock = {
            'rom': 'test', 'anti_version': 1, 'anti_version_source': 'verified-os3-base-firmware',
            'images': {name: {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
                       for name, data in self.payloads.items()},
            'archive': {'format': 'zip', 'members': self.members,
                        'compression': {'super.img': 'zstd'}},
        }

    def archive(self, boot=None, raw=None, duplicate=False, symlink=False, missing=False):
        path = self.root / 'input.zip'
        with zipfile.ZipFile(path, 'w') as z:
            if not missing:
                entry = zipfile.ZipInfo('boot_official.img')
                if symlink:
                    entry.create_system = 3
                    entry.external_attr = (stat.S_IFLNK | 0o777) << 16
                z.writestr(entry, self.payloads['boot.img'] if boot is None else boot)
            raw = self.payloads['super.img'] if raw is None else raw
            z.writestr('super.zst', zstandard.ZstdCompressor().compress(raw))
            z.writestr('boot_magisk.img', b'never install this')
            z.writestr('META-INF/com/google/android/update-binary', b'never execute this')
            z.writestr('firmware-update/frp.img', b'never extract this')
            if duplicate:
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore', UserWarning)
                    z.writestr('boot_official.img', self.payloads['boot.img'])
        self.lock['archive'].update(bytes=path.stat().st_size, sha256=stock.sha(path))
        return path

    def test_exact_payloads_only_and_zstd(self):
        archive = self.archive()
        before = stock.sha(archive)
        images = self.root / 'normalized/images'
        stock.unpack_rom(archive, images, self.lock)
        self.assertEqual({p.name for p in images.iterdir()}, {'boot.img', 'super.img', 'anti_version.txt'})
        for name, data in self.payloads.items():
            self.assertEqual((images / name).read_bytes(), data)
        self.assertEqual((images / 'anti_version.txt').read_text(), '1\n')
        self.assertEqual(stock.sha(archive), before)

    def test_wrong_archive_rejected_before_output(self):
        archive = self.archive()
        self.lock['archive']['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'archive identity'):
            stock.unpack_rom(archive, self.root / 'output', self.lock)
        self.assertFalse((self.root / 'output').exists())

    def test_wrong_image_rejected_even_with_matching_zip_identity(self):
        archive = self.archive(boot=b'x' * len(self.payloads['boot.img']))
        with self.assertRaisesRegex(ValueError, 'Wrong test input'):
            stock.unpack_rom(archive, self.root / 'output', self.lock)

    def test_duplicate_missing_and_symlink_members(self):
        for index, options in enumerate(({'duplicate': True}, {'missing': True}, {'symlink': True})):
            with self.subTest(options=options):
                archive = self.archive(**options)
                with self.assertRaisesRegex(ValueError, 'nonregular ROM member'):
                    stock.unpack_rom(archive, self.root / str(index), self.lock)

    def test_zstd_size_bounds(self):
        for index, raw in enumerate((self.payloads['super.img'][:-1], self.payloads['super.img'] + b'x')):
            with self.subTest(length=len(raw)):
                archive = self.archive(raw=raw)
                output = self.root / str(index)
                with self.assertRaisesRegex(ValueError, 'Truncated|exceeds'):
                    stock.unpack_rom(archive, output, self.lock)
                self.assertLessEqual((output / 'super.img').stat().st_size, len(self.payloads['super.img']))

    def test_output_cannot_be_overwritten(self):
        archive = self.archive()
        output = self.root / 'output'
        output.mkdir()
        marker = output / 'keep'
        marker.write_text('user data')
        with self.assertRaisesRegex(ValueError, 'exists'):
            stock.unpack_rom(archive, output, self.lock)
        self.assertEqual(marker.read_text(), 'user data')

    def test_mapping_cannot_escape_output(self):
        archive = self.archive()
        lock = copy.deepcopy(self.lock)
        lock['images']['../escape'] = lock['images'].pop('boot.img')
        with self.assertRaisesRegex(ValueError, 'Unsafe normalized'):
            stock.unpack_rom(archive, self.root / 'output', lock)

    def test_anti_provenance_is_required(self):
        archive = self.archive()
        del self.lock['anti_version_source']
        with self.assertRaisesRegex(ValueError, 'anti-version provenance'):
            stock.unpack_rom(archive, self.root / 'output', self.lock)

    def test_legacy_tgz(self):
        archive = self.root / 'legacy.tgz'
        lock = copy.deepcopy(self.lock)
        lock['archive'] = {'format': 'tgz'}
        payloads = dict(self.payloads, **{'anti_version.txt': b'1'})
        with tarfile.open(archive, 'w:gz') as t:
            for name, data in payloads.items():
                entry = tarfile.TarInfo('rom/images/' + name)
                entry.size = len(data)
                t.addfile(entry, io.BytesIO(data))
        lock['archive'].update(bytes=archive.stat().st_size, sha256=stock.sha(archive))
        stock.unpack_rom(archive, self.root / 'output', lock)


if __name__ == '__main__':
    unittest.main()
