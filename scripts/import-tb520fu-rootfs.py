#!/usr/bin/env python3
"""Import the hash-pinned common ARM64 userspace into a dedicated TB520FU rootfs."""
import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import subprocess
import urllib.request

REPO = Path(__file__).resolve().parents[1]
LOCK = REPO / 'external-and-mods/tb520fu/base-release.json'

def run(*args, **kwargs):
    return subprocess.run(args, check=True, text=True, **kwargs)

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('rootfs', type=Path)
    ap.add_argument('--cache', required=True, type=Path)
    a = ap.parse_args()
    root = a.rootfs.resolve()
    if os.geteuid() != 0:
        ap.error('root required for ownership-preserving filesystem import')
    if root == Path('/') or not (root / '.tb520fu-rootfs').is_file():
        ap.error('TB520FU dedicated rootfs marker required')
    lock = json.loads(LOCK.read_text())
    stamp = root / 'opt/tb520fu-base-release.json'
    if stamp.is_file():
        if json.loads(stamp.read_text()) != lock:
            ap.error('existing rootfs uses a different base release')
        print('Pinned common userspace already imported')
        return
    if (root / 'usr').exists():
        ap.error('rootfs already contains another userspace; choose a fresh directory')
    cache = a.cache.resolve(); cache.mkdir(parents=True, exist_ok=True)
    def get(item):
        name, expected = item
        dest = cache / name
        if not dest.is_file() or hashlib.file_digest(dest.open('rb'), 'sha256').hexdigest() != expected:
            url = f"https://github.com/{lock['repository']}/releases/download/{lock['tag']}/{name}"
            temp = dest.with_suffix(dest.suffix + '.part')
            urllib.request.urlretrieve(url, temp)
            if hashlib.file_digest(temp.open('rb'), 'sha256').hexdigest() != expected:
                raise ValueError('release asset SHA256 mismatch: ' + name)
            temp.replace(dest)
        print('Verified common userspace asset:', name, flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(get, lock['assets'].items()))
    unpacked = cache / 'unpacked'; unpacked.mkdir(exist_ok=True)
    run('7z', 'x', '-y', '-o' + str(unpacked), str(cache / next(iter(lock['assets']))))
    images = list(unpacked.rglob('*.img'))
    # The archive must contain exactly one complete SteamOS disk image.
    candidates = [f for f in images if f.stat().st_size > 1024**3]
    if len(candidates) != 1:
        raise ValueError('expected one complete SteamOS disk image')
    image = candidates[0]
    layout = json.loads(run('sfdisk', '--json', str(image), capture_output=True).stdout)['partitiontable']
    parts = layout['partitions']
    if layout['label'] != 'dos' or len(parts) != 3 or [x['type'] for x in parts] != ['c','83','83']:
        raise ValueError('unexpected common image partition layout')
    loop = run('losetup', '--read-only', '--find', '--show', '--partscan', str(image), capture_output=True).stdout.strip()
    mounted = []
    try:
        for index, target in [(2, root), (3, root / 'home')]:
            mountpoint = cache / f'mount-p{index}'; mountpoint.mkdir(exist_ok=True)
            run('mount', '-o', 'ro,noload', loop + f'p{index}', str(mountpoint)); mounted.append(mountpoint)
            target.mkdir(parents=True, exist_ok=True)
            run('rsync', '-aHAX', '--numeric-ids', '--exclude=/boot/**', str(mountpoint) + '/', str(target) + '/')
        run('readelf', '-h', str(root / 'usr/bin/bash'), capture_output=True)
        stamp.parent.mkdir(parents=True, exist_ok=True); stamp.write_text(json.dumps(lock, indent=2)+'\n')
    finally:
        for m in reversed(mounted): run('umount', str(m))
        run('losetup', '-d', loop)
    print('Common ARM64 userspace imported; TB520FU kernel/runtime override is required')

if __name__ == '__main__':
    main()
