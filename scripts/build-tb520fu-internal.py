#!/usr/bin/env python3
"""Pack TB520FU internal-install images from its completed external image.

Only regular image files and private loop devices are written. No tablet access.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import struct
import subprocess
import uuid

REPO = Path(__file__).resolve().parents[1]


def run(*args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, **kwargs)


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for data in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(data)
    return h.hexdigest()


def regular(path):
    assert not path.is_symlink() and stat.S_ISREG(path.stat().st_mode), path


def verify_kernel_modules(root, kout):
    """Require the installed module payload to match the selected kernel output."""
    release = '7.2.6-tb520fu-steamos'
    expected = kout / 'modules' / release
    installed = root / 'usr/lib/modules' / release
    regular(expected / 'vmlinuz')
    if sha(expected / 'vmlinuz') != sha(kout / 'boot/Image'):
        raise ValueError('kernel output Image differs from its module carrier')

    def inventory(directory):
        if not directory.is_dir():
            raise ValueError(f'module directory missing: {directory}')
        entries = {}
        for path in directory.rglob('*'):
            name = path.relative_to(directory).as_posix()
            if path.is_symlink():
                entries[name] = ('link', os.readlink(path))
            elif path.is_file():
                entries[name] = ('file', sha(path))
        return entries

    if inventory(installed) != inventory(expected):
        raise ValueError('installed modules differ from the selected kernel output; rebuild the rootfs')


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def replace_link(path, target):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        assert not path.is_dir(), path
        path.unlink()
    path.symlink_to(target)


def inspect_sparse(sparse, raw):
    """Compare Android sparse contents with the raw filesystem, including holes."""
    h = hashlib.sha256()
    zeros = b'\0' * (8 * 1024 * 1024)
    with sparse.open('rb') as s, raw.open('rb') as r:
        magic, major, minor, fh, ch, block, total, chunks, checksum = struct.unpack('<I4H4I', s.read(28))
        assert (magic, major, minor, fh, ch, block) == (0xed26ff3a, 1, 0, 28, 12, 4096)
        assert total * block == raw.stat().st_size and not checksum
        seen = 0
        for _ in range(chunks):
            kind, reserved, blocks, size = struct.unpack('<2H2I', s.read(12))
            count = blocks * block
            assert not reserved
            if kind == 0xcac1:
                assert size == 12 + count
            elif kind == 0xcac2:
                assert size == 16
                pattern = s.read(4)
            elif kind == 0xcac3:
                assert size == 12
            else:
                raise ValueError(f'unsupported sparse chunk {kind:x}')
            while count:
                n = min(count, len(zeros))
                data = s.read(n) if kind == 0xcac1 else (pattern * (n // 4) if kind == 0xcac2 else zeros[:n])
                assert len(data) == n and data == r.read(n), 'sparse/raw mismatch'
                h.update(data)
                count -= n
            seen += blocks
        assert seen == total and not s.read(1) and not r.read(1)
    return {'expanded_bytes': total * block, 'chunks': chunks, 'raw_sha256': h.hexdigest()}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source-image', type=Path, required=True)
    ap.add_argument('--kernel-out', type=Path, required=True)
    ap.add_argument('--uefi-image', type=Path, required=True)
    ap.add_argument('--uefi-sha256', required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--userdata-gib', type=int, default=20)
    a = ap.parse_args()
    assert os.geteuid() == 0, 'root is required for private loop mounts'
    src, kout, uefi = a.source_image.resolve(), a.kernel_out.resolve(), a.uefi_image.resolve()
    for p in (src, uefi, kout / 'boot/Image'):
        regular(p)
    assert sha(uefi) == a.uefi_sha256, 'UEFI hash mismatch'
    assert uefi.read_bytes()[:8] == b'ANDROID!'
    source_commit = (kout / 'TB520FU-SOURCE').read_text().strip()
    assert source_commit == '972c5ce4d2955bb0382a2101f4e22c5185cea6ba'
    config = (kout / 'config-7.2.6-tb520fu-steamos').read_text()
    for key in ('SCSI_UFSHCD', 'SCSI_UFS_QCOM', 'EXT4_FS', 'OVERLAY_FS', 'EFI_STUB'):
        assert f'CONFIG_{key}=y\n' in config, key
    assert 16 <= a.userdata_gib <= 64
    out = a.output.absolute()
    assert not out.exists() and out.parent.is_dir(), 'choose a fresh output directory'
    out.mkdir()
    write(out / '.tb520fu-internal-build', 'TB520FU internal image staging\n')
    stage = out / '.mounts'
    stage.mkdir()
    loops, mounts = [], []
    root_uuid = str(uuid.uuid4())
    raw, sup = out / 'userdata.img', out / 'super.img'
    with raw.open('xb') as f:
        f.truncate(a.userdata_gib * 1024**3)
    with sup.open('xb') as f:
        f.truncate(512 * 1024**2)
    try:
        source_loop = subprocess.check_output(['losetup', '--find', '--show', '--read-only', '--partscan', str(src)], text=True).strip()
        loops.append(source_loop)
        rootsrc, homesrc, bootsrc, target, boot = [stage / n for n in ('source-root', 'source-home', 'source-boot', 'root', 'boot')]
        for p in (rootsrc, homesrc, bootsrc, target, boot):
            p.mkdir()
        for num, p, fs in ((2, rootsrc, 'ext4'), (3, homesrc, 'ext4'), (1, bootsrc, 'vfat')):
            run('mount', '-t', fs, '-o', 'ro,noload' if fs == 'ext4' else 'ro', source_loop + f'p{num}', p)
            mounts.append(p)
        assert (rootsrc / '.tb520fu-rootfs').is_file()
        identity = json.loads((rootsrc / 'usr/share/steamos-arm/tb520fu.json').read_text())
        assert identity['device'] == 'lenovo,tb520fu' and identity['source_commit'] == source_commit
        assert sha(bootsrc / 'Image') == sha(kout / 'boot/Image'), 'source image kernel differs'
        verify_kernel_modules(rootsrc, kout)
        run('mkfs.ext4', '-F', '-L', 'userdata', '-U', root_uuid, '-m', '1', '-E', 'lazy_itable_init=0,lazy_journal_init=0', raw)
        run('mkfs.fat', '-F', '32', '-S', '4096', '-s', '1', '-n', 'TB520BOOT', sup)
        for image, p, fs in ((raw, target, 'ext4'), (sup, boot, 'vfat')):
            loop = subprocess.check_output(['losetup', '--find', '--show', str(image)], text=True).strip()
            loops.append(loop)
            run('mount', '-t', fs, loop, p)
            mounts.append(p)
        print('Copying TB520FU system and home into userdata', flush=True)
        run('rsync', '-aHAX', '--numeric-ids', str(rootsrc) + '/', str(target) + '/')
        run('rsync', '-aHAX', '--numeric-ids', str(homesrc) + '/', str(target / 'home') + '/')
        fstab = (f'UUID={root_uuid} / ext4 defaults,noatime,x-systemd.growfs 0 1\n'
                 'PARTLABEL=super /boot vfat defaults,umask=0077,nofail,x-systemd.device-timeout=10s 0 2\n')
        for layer in ('etc', 'var/lib/overlays/etc/upper'):
            write(target / layer / 'fstab', fstab)
            write(target / layer / 'machine-id', '')
            # The external layout's grow-home and the inherited repart recipe
            # must never change the Android partition table on an internal install.
            for service in ('steamos-sm8550-expand-home.service', 'systemd-repart.service', 'home.mount'):
                replace_link(target / layer / 'systemd/system' / service, '/dev/null')
        write(target / 'opt/steamos-sm8650/IMAGE.txt',
              f'device=TB520FU\nlayout=boot_a:UEFI + super:FAT32 + userdata:ext4-root-and-home\nroot_uuid={root_uuid}\nexpand=systemd-growfs-root.service (filesystem only)\n')
        marker = 'steamos-tb520fu-internal-' + root_uuid
        write(boot / marker, 'TB520FU internal boot filesystem\n')
        (boot / 'EFI/BOOT').mkdir(parents=True)
        (boot / 'dtb').mkdir()
        for name in ('BOOTAA64.EFI', 'QCOMRAMP.EFI'):
            shutil.copy2(bootsrc / 'EFI/BOOT' / name, boot / 'EFI/BOOT' / name)
        shutil.copy2(kout / 'boot/Image', boot / 'Image')
        dtbs = [('Tianma', 'sm8650-lenovo-tb520fu.dtb'), ('BOE', 'sm8650-lenovo-tb520fu-boe.dtb')]
        for _, name in dtbs:
            shutil.copy2(kout / 'dtbs' / name, boot / 'dtb' / name)
        cmdline = (f'root=UUID={root_uuid} rootfstype=ext4 rw rootwait '
                   'steamos.bootlabel=super firmware_class.path=/usr/lib/firmware/steamos-arm/tb520fu '
                   'efi=novamap,debug fw_devlink.sync_state=timeout drm_client_lib.active=none '
                   'earlycon=efifb console=tty0 fbcon=nodefer loglevel=4 '
                   'printk.time=1 consoleblank=0 initcall_debug '
                   'log_buf_len=4M tb520fu.diagnostics=1')
        # Match the working Y703 test-7 EFI-stub boot path. The RAM-partition
        # chainloader faults before Linux on TB520FU and is not a usable fallback.
        grub = 'set timeout=8\nset default=0\nset gfxpayload=keep\n'
        ramp = 'set timeout=8\nset default=0\n'
        from tb520fu_display_diagnostics import make_internal_display_dtb

        for panel, native_name in dtbs:
            name = native_name.removesuffix('.dtb') + '-internal-display.dtb'
            make_internal_display_dtb(boot / 'dtb' / native_name,
                                      boot / 'dtb' / name)
            search = f'    search --no-floppy --file /{marker} --set=root\n'
            grub += (f'menuentry "SteamOS TB520FU ({panel}, internal UFS)" {{\n' + search +
                     f'    devicetree /dtb/{name}\n    linux /Image {cmdline}\n}}\n')
            ramp += (f'menuentry "SteamOS TB520FU ({panel}, RAM partition handoff)" {{\n' + search +
                     f'    devicetree /dtb/{name}\n    qcomfdtmem source rampartition\n    linuxdirect /Image {cmdline}\n}}\n')
        from tb520fu_display_diagnostics import make_firmware_display_dtb

        diagnostic_dtb = 'sm8650-lenovo-tb520fu-efifb.dtb'
        make_firmware_display_dtb(boot / 'dtb/sm8650-lenovo-tb520fu.dtb',
                                  boot / 'dtb' / diagnostic_dtb)
        # Keep the firmware-only diagnostic console available; native display
        # must not perform a fbdev modeset during component binding.
        diagnostic_cmdline = cmdline.replace('drm_client_lib.active=none',
                                             'drm_client_lib.active=fbdev')
        grub += ('menuentry "Tianma: firmware display diagnostics" {\n' + search +
                 f'    devicetree /dtb/{diagnostic_dtb}\n'
                 f'    linux /Image {diagnostic_cmdline} clk_ignore_unused '
                 'regulator_ignore_unused pd_ignore_unused '
                 'systemd.unit=multi-user.target\n}\n')
        write(boot / 'boot/grub/grub.cfg', grub)
        write(boot / 'EFI/BOOT/grub.cfg', 'configfile /boot/grub/grub.cfg\n')
        write(boot / 'EFI/BOOT/qcomramp.cfg', ramp)
        assert (target / 'usr/lib/modules/7.2.6-tb520fu-steamos').is_dir()
        assert (target / 'usr/bin/steamos-set-root-password').exists()
        assert (target / 'etc/fstab').read_text() == fstab
        assert (target / 'var/lib/overlays/etc/upper/fstab').read_text() == fstab
        assert (target / 'home/steamos').is_dir()
        assert stat.S_IMODE((target / 'usr/bin/sudo').stat().st_mode) & stat.S_ISUID
        assert sha(boot / 'Image') == sha(kout / 'boot/Image')
        shutil.copy2(uefi, out / 'boot.img')
        (out / 'boot-configuration.txt').write_text(grub)
        os.sync()
    finally:
        for p in reversed(mounts):
            run('umount', p)
        for loop in reversed(loops):
            run('losetup', '--detach', loop)
    run('e2fsck', '-f', '-n', raw)
    run('fsck.fat', '-n', sup)
    print('Converting userdata to Android sparse format', flush=True)
    run('img2simg', raw, out / 'userdata.simg', '4096')
    sparse = inspect_sparse(out / 'userdata.simg', raw)
    report = {'device': 'TB520FU', 'hardware_boot_tested': False,
              'kernel_source_commit': source_commit, 'kernel_release': '7.2.6-tb520fu-steamos',
              'uefi_sha256': a.uefi_sha256, 'source_external_image': str(src),
              'root_uuid': root_uuid, 'userdata_sparse': sparse,
              'boot_path': 'boot_a UEFI -> super FAT32 GRUB -> userdata ext4 root and home',
              'default_panel': 'Tianma', 'other_panel': 'BOE',
              'kernel_image_sha256': sha(kout / 'boot/Image'),
              'files': {name: {'bytes': (out / name).stat().st_size, 'sha256': sha(out / name)}
                        for name in ('boot.img', 'super.img', 'userdata.simg')}}
    write(out / 'internal-image.json', json.dumps(report, indent=2) + '\n')
    write(out / 'SHA256SUMS', ''.join(f"{v['sha256']}  {k}\n" for k, v in report['files'].items()))
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()
