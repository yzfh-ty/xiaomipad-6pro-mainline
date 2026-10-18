#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Prepare the pinned OS4 ZIP, original KernelSU and Ubuntu build inputs."""
import argparse
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import urllib.parse

PROJECT = Path(__file__).resolve().parents[1]
LOCAL = PROJECT / 'tools/local'
spec = importlib.util.spec_from_file_location('stock_rom', PROJECT / 'tools/lib/stock-rom.py')
stock = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stock)


def run(*args, **kwargs):
    subprocess.run([str(a) for a in args], check=True, **kwargs)


def download(url, destination, digest, size=None):
    if not url or any(ord(c) < 32 for c in url):
        raise ValueError('Set the Android ROM URL input to a current HTTPS direct link')
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Download inputs must be HTTPS URLs without credentials')
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and stock.sha(destination) == digest:
        return
    temporary = destination.with_suffix(destination.suffix + '.part')
    try:
        run('curl', '--fail', '--location', '--proto', '=https', '--proto-redir', '=https',
            '--retry', '4', '--retry-delay', '5', '--output', temporary, url)
    except subprocess.CalledProcessError:
        # Signed URL query strings are temporary access credentials, not log data.
        raise ValueError('ROM download failed; check URL validity and expiration') from None
    if stock.sha(temporary) != digest or (size is not None and temporary.stat().st_size != size):
        temporary.unlink()
        raise ValueError(f'Download identity mismatch: {destination.name}')
    temporary.replace(destination)


def unpack_rom(archive, images):
    return stock.unpack_rom(archive, images)


def copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    target.chmod(0o644)


def firmware_pool():
    """Map the reviewed public board firmware into the builders' input layout.

    Android's ROM changes independently of Ubuntu's firmware closure. Keep
    Ubuntu's validated payloads, instead of adopting untested OS3 DSP blobs.
    """
    baseline = PROJECT / 'device/firmware'
    manifest = baseline / 'firmware.manifest'
    if stock.sha(manifest) != '012c413e0a5d5c3c14631fbdfe50da5c51e95ffc1ae431b8d93f776538b65ba2':
        raise ValueError('Board firmware manifest identity mismatch')
    for line in manifest.read_text().splitlines():
        digest, name = line.split('  ', 1)
        if not name.startswith('/usr/lib/firmware/') or '..' in PurePosixPath(name).parts:
            raise ValueError('Unexpected board firmware manifest path')
        if stock.sha(baseline / name.lstrip('/')) != digest:
            raise ValueError(f'Board firmware identity mismatch: {name}')
    firmware = baseline / 'usr/lib/firmware'
    pool = LOCAL / 'firmware-liuqin'
    if pool.exists():
        raise ValueError('Firmware pool exists; use a fresh checkout')
    for name in ('novatek_nt36532_m81_fw_csot.bin', 'novatek_nt36532_m81_fw_tm.bin'):
        copy(firmware / 'novatek/liuqin' / name, pool / 'touch-nt36532/vendor/firmware' / name)
    copy(firmware / 'qcom/sm8475/liuqin/a730_zap.mbn', pool / 'gpu-adreno730/vendor/a730_zap.mbn')
    for name in ('a730_sqe.fw', 'gmu_gen70000.bin'):
        copy(firmware / 'updates/qcom' / name, pool / 'gpu-adreno730/vendor' / name)
    for path in (firmware / 'qca').iterdir():
        if re.fullmatch(r'(hpbtfw2[01]\.tlv|hpnv2[01]g?\.(bin|b[0-9a-f]+))', path.name):
            copy(path, pool / 'bt-qca6490/vendor/bt_firmware/image' / path.name)
    for path in (firmware / 'qcom/sm8475/liuqin').iterdir():
        if re.fullmatch(r'(adsp|cdsp|slpi)\.(mbn|b[0-9a-f]+)', path.name):
            copy(path, pool / 'dsp-sm8475/vendor/qcom/sm8475/liuqin' / path.name)
    copy(firmware / 'ath11k/WCN6855/hw2.0/board.bin',
         pool / 'wlan-qca6490/vendor/firmware_mnt/image/qca6490/bd_m81.elf')
    for name in ('amss.bin.zst', 'm3.bin.zst', 'board-2.bin.zst', 'regdb.bin.zst'):
        copy(firmware / 'ath11k/WCN6855/hw2.0' / name,
             pool / 'wlan-qca6490/upstream/WCN6855/hw2.0' / name)
    for name in ('regulatory.db', 'regulatory.db.p7s'):
        copy(firmware / name, pool / 'regulatory/upstream' / name)
    shutil.copytree(firmware / 'updates/ath11k/WCN6855', PROJECT / 'out/wlan-source-check')
    # The firmware/initramfs builders retain their pinned payload checks.
    return pool


def checkout(url, commit, destination):
    destination.mkdir(parents=True)
    run('git', 'init', '-q', destination)
    run('git', '-C', destination, 'fetch', '--depth=1', url, commit)
    run('git', '-C', destination, 'checkout', '--detach', 'FETCH_HEAD')
    actual = subprocess.check_output(['git', '-C', str(destination), 'rev-parse', 'HEAD'], text=True).strip()
    if actual != commit:
        raise ValueError('Source checkout differs from the pinned commit')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom-archive', type=Path, help='Use the exact local ZIP instead of downloading')
    stages = parser.add_mutually_exclusive_group()
    stages.add_argument('--rom-only', action='store_true', help='Normalize ROM and check device trees, then stop')
    stages.add_argument('--download-only', action='store_true', help='Cache the pinned ZIP before lengthy runner setup')
    args = parser.parse_args()
    lock = stock.table()
    archive = args.rom_archive.resolve() if args.rom_archive else LOCAL / 'downloads' / lock['archive']['name']
    if not args.rom_archive:
        download(os.environ.get('ANDROID_ROM_URL') or lock['archive'].get('url'), archive,
                 lock['archive']['sha256'], lock['archive']['bytes'])
    if args.download_only:
        if args.rom_archive and (archive.stat().st_size != lock['archive']['bytes'] or
                                 stock.sha(archive) != lock['archive']['sha256']):
            raise ValueError('ROM archive identity mismatch')
        print('Pinned ROM ZIP cached and verified; no URL is stored in the artifacts.')
        return
    rom = LOCAL / 'roms/liuqin' / lock['rom']
    images = rom / 'images'
    unpack_rom(archive, images)
    if not args.rom_archive:
        archive.unlink()
    base, overlays = stock.split_device_trees(images, rom / 'analysis')
    run('python3', PROJECT / 'tools/lib/verify-stock-dt.py', '--base-dir', base, '--overlay-dir', overlays)
    if args.rom_only:
        print('ROM normalization and stock device-tree checks passed. No tablet was accessed.')
        return
    sevenzip_dir = LOCAL / '7zip'
    sevenzip_dir.mkdir(parents=True)
    sevenzip_archive = LOCAL / 'downloads/7z2603-linux-x64.tar.xz'
    download('https://github.com/ip7z/7zip/releases/download/26.03/7z2603-linux-x64.tar.xz',
             sevenzip_archive, 'dc99eff5008f1ab79bd7084c68513701547a808a89502bf4133683535ab3c695')
    run('tar', '-xJf', sevenzip_archive, '-C', sevenzip_dir)
    sevenzip = sevenzip_dir / '7zz'
    work = PROJECT / 'out/stock-extraction'
    work.mkdir(parents=True)
    run(sevenzip, 'x', '-y', f'-o{work}', images / 'super.img', 'vendor_a.img', stdout=subprocess.DEVNULL)
    vendor = rom / 'extracted/super-work/vendor-extract'
    vendor.parent.mkdir(parents=True)
    run('fsck.erofs', f'--extract={vendor}', work / 'vendor_a.img')
    (work / 'vendor_a.img').unlink()
    (PROJECT / 'out/stock-rom-verified.json').write_text(json.dumps(lock, indent=2) + '\n')
    # Identities were checked above. Reclaim space; ROM payloads are never uploaded.
    for image in images.iterdir():
        if image.name not in ('boot.img', 'anti_version.txt'):
            image.unlink()
    run('sh', PROJECT / 'tools/build-liuqin-ubuntu-desktop-rootfs.sh', 'download')
    run('sh', PROJECT / 'tools/build-liuqin-ubuntu-desktop-rootfs.sh', 'casper')
    run('sudo', '-n', 'sh', PROJECT / 'tools/build-liuqin-ubuntu-desktop-rootfs.sh', 'extract')
    # Fail before slow component builds if this host produces an unknown
    # desktop manifest. The assembly script owns the exact allowed identities.
    run('sudo', '-n', 'sh', PROJECT / 'tools/build-liuqin-native-root.sh', 'verify-desktop')
    ubuntu_dir = LOCAL / 'ubuntu-desktop-26.04-arm64'
    (ubuntu_dir / 'ubuntu-26.04-desktop-arm64.iso').unlink()
    shutil.rmtree(ubuntu_dir / 'iso')
    firmware_pool()
    checkout('https://github.com/linux-msm/audioreach-topology.git',
             '2af1f1ebb8d4fd03b5f53891467ddde2e208a8a0', LOCAL / 'audioreach-topology')
    shutil.rmtree(work)
    for tool in ('busybox-arm64', 'aosp-mkbootimg', 'kernelsu-assets'):
        run('sh', PROJECT / f'tools/fetch-{tool}.sh')
    ksu = json.loads((PROJECT / 'tools/lib/kernelsu-assets.json').read_text())
    assets = LOCAL / 'downloads/kernelsu' / ksu['version']
    run('python3', PROJECT / 'tools/patch-android-boot-ksu.py', '--boot', images / 'boot.img',
        '--ksuinit', assets / ksu['assets']['ksuinit']['name'], '--lkm', assets / ksu['assets']['lkm']['name'],
        '--out', PROJECT / 'out/android-os4/boot-ksu.img', '--report', PROJECT / 'out/android-os4/patch-report.txt')
    run('sudo', '-n', 'python3', PROJECT / 'tools/prepare-image-inputs.py', 'run', cwd=PROJECT)


if __name__ == '__main__':
    main()
