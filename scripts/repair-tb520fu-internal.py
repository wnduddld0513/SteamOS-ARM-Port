#!/usr/bin/env python3
"""Apply the TB520FU installer fixes to an existing internal-install bundle.

Only copies in a fresh output directory are mounted or changed; boot.img and
super.img are carried over unchanged. This does not flash a device.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess


HERE = Path(__file__).resolve().parent


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


installer = load('tb520fu_installer', 'install-tb520fu.py')
packer = load('tb520fu_packer', 'build-tb520fu-internal.py')
run = packer.run


def inventory(root):
    """Compare content, ownership, modes, links, devices and extended attributes."""
    result = {}
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            path = Path(directory) / name
            info = path.lstat()
            key = path.relative_to(root).as_posix()
            attrs = tuple(sorted(
                (n, os.getxattr(path, n, follow_symlinks=False))
                for n in os.listxattr(path, follow_symlinks=False)))
            if stat.S_ISLNK(info.st_mode):
                content = os.readlink(path)
            elif stat.S_ISREG(info.st_mode):
                content = packer.sha(path)
            else:
                content = info.st_rdev
            result[key] = (info.st_mode, info.st_uid, info.st_gid, content, attrs)
    return result


def changed_paths(before, after):
    return {name for name in before.keys() | after.keys()
            if before.get(name) != after.get(name)}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--userdata-raw', type=Path, required=True)
    ap.add_argument('--super-image', type=Path, required=True)
    ap.add_argument('--uefi-image', type=Path, required=True)
    ap.add_argument('--kernel-out', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    if os.geteuid() != 0:
        raise ValueError('root required for private image mounts')
    for source in (args.userdata_raw, args.super_image, args.uefi_image):
        packer.regular(source)
    with args.uefi_image.open('rb') as image:
        assert image.read(8) == b'ANDROID!'
    out = args.output.absolute()
    assert out.parent.is_dir() and not out.exists(), 'choose a fresh output directory'
    out.mkdir()
    raw, boot_image = out / 'userdata.img', out / 'super.img'
    run('/usr/bin/cp', '--sparse=always', args.userdata_raw, raw)
    shutil.copyfile(args.super_image, boot_image)
    shutil.copyfile(args.uefi_image, out / 'boot.img')
    stage = out / '.mounts'
    root, boot = stage / 'root', stage / 'boot'
    root.mkdir(parents=True)
    boot.mkdir()
    loops, mounts = [], []
    try:
        for image, mountpoint, kind, options in ((raw, root, 'ext4', 'noatime'),
                                                 (boot_image, boot, 'vfat', 'ro')):
            loop = subprocess.check_output(
                ['/usr/sbin/losetup', '--find', '--show', str(image)], text=True).strip()
            loops.append(loop)
            run('/usr/bin/mount', '-t', kind, '-o', options, loop, mountpoint)
            mounts.append(mountpoint)
        assert (root / '.tb520fu-rootfs').is_file()
        identity = json.loads((root / 'usr/share/steamos-arm/tb520fu.json').read_text())
        assert identity['device'] == 'lenovo,tb520fu'
        assert identity['source_commit'] == installer.SOURCE_COMMIT
        packer.verify_kernel_modules(root, args.kernel_out)
        assert packer.sha(boot / 'Image') == packer.sha(args.kernel_out / 'boot/Image')
        print('Verified matching kernel/module payload; inventorying original contents', flush=True)
        before = inventory(root)
        manifest = json.loads((installer.DEVICE / 'firmware-manifest.json').read_text())
        specs = {v['destination']: v for v in manifest['files'].values()}
        payloads, obsolete = {}, []
        for name in installer.QCA_FIRMWARE:
            stock = 'usr/lib/firmware/' + name
            old = installer.PRIVATE_FW + '/' + name
            data = installer.destination(root, old).read_bytes()
            spec = specs[stock]
            assert len(data) == spec['size']
            assert hashlib.sha256(data).hexdigest() == spec['sha256']
            target = installer.firmware_destination(stock)
            assert not installer.destination(root, target).exists()
            payloads[target] = data
            obsolete.append(old)
        units = ('set-bluetooth-mac-address.service', 'scx.service')
        assert set(units) <= set(installer.MASKED)
        masks = [prefix + unit for unit in units for prefix in (
            'etc/systemd/system/', 'var/lib/overlays/etc/upper/systemd/system/')]
        for name in obsolete + masks:
            installer.leaf_destination(root, name)
        allowed = set(payloads) | set(obsolete) | set(masks)
        for name in payloads:
            for parent in Path(name).parents:
                if parent != Path('.'):
                    allowed.add(parent.as_posix())
        for name, data in payloads.items():
            installer.write_file(root, name, data)
        for name in obsolete:
            installer.leaf_destination(root, name).unlink()
        installer.mask_system_services(root, units)
        root_uuid = subprocess.check_output(
            ['/usr/sbin/blkid', '-s', 'UUID', '-o', 'value', str(raw)], text=True).strip()
        assert f'root=UUID={root_uuid} ' in (boot / 'boot/grub/grub.cfg').read_text()
        os.sync()

        after = inventory(root)
        changes = changed_paths(before, after)
        assert changes <= allowed, f'unexpected rootfs changes: {sorted(changes - allowed)}'
        for name, data in payloads.items():
            assert installer.destination(root, name).read_bytes() == data
        for name in obsolete:
            assert not (root / name).exists()
        for name in masks:
            assert (root / name).readlink() == Path('/dev/null')
        print('Scoped rootfs changes: ' + ', '.join(sorted(changes)), flush=True)
    finally:
        for mountpoint in reversed(mounts):
            run('/usr/bin/umount', mountpoint)
        for loop in reversed(loops):
            run('/usr/sbin/losetup', '--detach', loop)

    run('/usr/sbin/e2fsck', '-f', '-n', raw)
    assert packer.sha(boot_image) == packer.sha(args.super_image)
    assert packer.sha(out / 'boot.img') == packer.sha(args.uefi_image)
    run('/usr/bin/img2simg', raw, out / 'userdata.simg', '4096')
    sparse = packer.inspect_sparse(out / 'userdata.simg', raw)
    files = {name: {'bytes': (out / name).stat().st_size, 'sha256': packer.sha(out / name)}
             for name in ('boot.img', 'super.img', 'userdata.simg')}
    metadata = {
        'device': 'TB520FU', 'hardware_boot_tested': False,
        'kernel_source_commit': installer.SOURCE_COMMIT, 'root_uuid': root_uuid,
        'changes': sorted(changes), 'userdata_sparse': sparse, 'files': files,
    }
    packer.write(out / 'internal-image.json', json.dumps(metadata, indent=2) + '\n')
    packer.write(out / 'SHA256SUMS', ''.join(
        f"{item['sha256']}  {name}\n" for name, item in files.items()))
    print(json.dumps(metadata, indent=2), flush=True)


if __name__ == '__main__':
    main()
