#!/usr/bin/env python3
"""Install the opt-in TB520FU stack; --check-firmware performs no writes."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import tarfile

REPO = Path(__file__).resolve().parents[1]
DEVICE = REPO / 'external-and-mods/tb520fu'
PRIVATE_FW = 'usr/lib/firmware/steamos-arm/tb520fu'
QCA_FIRMWARE = (
    'qcom/sm8650/lenovo/tb520fu/hmtbtfw20.tlv',
    'qcom/sm8650/lenovo/tb520fu/hmtnv20_Lapis.bin',
)
SOURCE_COMMIT = 'f0daedc104c710f2e4c9cde1d654a40d4854bbf2'
FIRMWARE_SHA = '315f7d7f349fef84fbe05211fbbc55eaad3d93c750326bc80baca6e849da4328'
MASKED = (
    'konkrd.service', 'konkr-sleep.service', 'konkr-pd-kick.service',
    'pocket-s2-controller.service', 'sm8550-fixpad.service',
    'sm8550-inputplumber-ext-hid.service', 'sm8550-audio-setup.service',
    'sm8550-bluetooth-setup.service', 'steamos-arm-power.service',
    # Deckard's EEPROM MAC writer; TB520FU has no such EEPROM.
    'set-bluetooth-mac-address.service',
    # The common SM8650 kernel has no sched_ext, so scx.service never runs
    # there. The TB520FU kernel enables it; scx_lavd then stalls the tablet.
    'scx.service',
    'steamos-arm-vpower.service', 'steamos-arm-tablet-boot-ok.service',
    'steamos-arm-tablet-firmware.service', 'steamos-arm-update.service',
    'steamos-arm-update-cleanup.service',
)

def valid_name(name):
    p = PurePosixPath(name)
    if not name or p.is_absolute() or '..' in p.parts or str(p) != name:
        raise ValueError('invalid relative path: ' + name)
    return p

def destination(root, name):
    valid_name(name)
    dest = root / name
    if not dest.resolve().is_relative_to(root):
        raise ValueError('destination escapes rootfs: ' + name)
    return dest

def leaf_destination(root, name):
    # Replacement/removal never follows the final symlink (systemd masks use
    # /dev/null), but every parent must stay inside the dedicated rootfs.
    valid_name(name)
    dest = root / name
    if not dest.parent.resolve().is_relative_to(root):
        raise ValueError('destination parent escapes rootfs: ' + name)
    return dest

def firmware_destination(name):
    if name.startswith('usr/lib/firmware/'):
        name = name.removeprefix('usr/lib/firmware/')
        # btqca prefixes both DT firmware-name entries with "qca/".
        if name in QCA_FIRMWARE:
            name = 'qca/' + name
        return PRIVATE_FW + '/' + name
    if name.startswith('usr/share/qcom/sm8650/Lenovo/tb520fu/'):
        return name
    raise ValueError('unexpected firmware namespace: ' + name)

def firmware(archive):
    if hashlib.sha256(archive.read_bytes()).hexdigest() != FIRMWARE_SHA:
        raise ValueError('stock archive SHA256 differs from the pinned TB520FU archive')
    entries = json.loads((DEVICE / 'firmware-manifest.json').read_text())['files']
    expected = {v['destination']: v for v in entries.values()}
    if len(expected) != len(entries):
        raise ValueError('duplicate firmware destinations')
    payloads = {}
    with tarfile.open(archive, 'r:gz') as tar:
        members = tar.getmembers()
        names = [m.name for m in members]
        if len(names) != len(set(names)) or set(names) != set(expected):
            raise ValueError('archive file set differs from firmware manifest')
        for m in members:
            valid_name(m.name)
            spec = expected[m.name]
            if not m.isfile() or m.size != spec['size']:
                raise ValueError('invalid firmware member: ' + m.name)
            data = tar.extractfile(m).read()
            if hashlib.sha256(data).hexdigest() != spec['sha256']:
                raise ValueError('firmware member hash mismatch: ' + m.name)
            target = firmware_destination(m.name)
            payloads[target] = data
    return payloads

def runtime_files(stage):
    manifest = json.loads((stage / 'TB520FU-RUNTIME.json').read_text())
    if manifest['source_commit'] != SOURCE_COMMIT:
        raise ValueError('runtime uses a different TB520FU source commit')
    result = {}
    for name, spec in manifest['files'].items():
        valid_name(name)
        src = stage / name
        if not src.resolve().is_relative_to(stage):
            raise ValueError('runtime path escapes stage: ' + name)
        if 'link' in spec:
            if not src.is_symlink() or src.readlink().as_posix() != spec['link']:
                raise ValueError('runtime link mismatch: ' + name)
            if PurePosixPath(spec['link']).is_absolute():
                raise ValueError('absolute runtime symlink: ' + name)
            result[name] = ('link', spec['link'], 0)
        else:
            data = src.read_bytes()
            if len(data) != spec['size'] or hashlib.sha256(data).hexdigest() != spec['sha256']:
                raise ValueError('runtime hash mismatch: ' + name)
            result[name] = ('file', data, spec['mode'])
    required = {'usr/bin/hexagonrpcd', 'usr/bin/inputplumber',
                'usr/libexec/tb321fu-imu-bridge', 'usr/libexec/iio-sensor-proxy',
                PRIVATE_FW + '/qcom/sm8650/Lenovo-Yoga-TB520FU-tplg.bin'}
    if not required.issubset(result) or not any(n.startswith('usr/lib/libssc.so.') for n in result):
        raise ValueError('runtime missing sensors, input or topology outputs')
    return result

def write_file(root, name, data, mode=0o644):
    p = destination(root, name)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    p.chmod(mode)

def mask_system_services(root, units):
    paths = [leaf_destination(root, prefix + unit) for unit in units
             for prefix in ('etc/systemd/system/',
                            'var/lib/overlays/etc/upper/systemd/system/')]
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() or path.is_symlink():
            path.unlink()
        path.symlink_to('/dev/null')

def install(root, payloads, runtime):
    root = root.resolve(strict=True)
    if root == Path('/') or not (root / '.tb520fu-rootfs').is_file() or not (root / 'usr/bin/bash').is_file():
        raise ValueError('use a dedicated staging rootfs created by make-steamos-tb520fu.sh')
    # Validate every target before any write (including pre-existing symlinks).
    overlay = REPO / 'tb520fu-overlay'
    overlay_files = {p.relative_to(overlay).as_posix(): p for p in overlay.rglob('*') if p.is_file()}
    remove = [
        'usr/share/wireplumber/wireplumber.conf.d/51-sm8550-hifi-priority.conf',
        'usr/share/wireplumber/wireplumber.conf.d/52-sm8550-alsa.conf',
        'etc/wireplumber/wireplumber.conf.d/52-sm8550-alsa.conf',
        'etc/wireplumber/wireplumber.conf.d/53-konkr-audio.conf',
        'etc/wireplumber/wireplumber.conf.d/54-konkr-quantum.conf',
        'etc/wireplumber/wireplumber.conf.d/55-konkr-speaker.conf',
        'etc/wireplumber/wireplumber.conf.d/99-konkr-no-mic-tracker.conf',
        'etc/pipewire/pipewire.conf.d/99-konkr-quantum.conf',
        'usr/share/pipewire/pipewire.conf.d/99-sm8550-buffers.conf',
        'usr/share/pipewire/pipewire-pulse.conf.d/99-sm8550-buffers.conf',
        'usr/lib/systemd/system/systemd-suspend.service.d/10-konkr-standby.conf',
        'usr/lib/systemd/user/wireplumber.service.d/60-wait-audio-setup.conf',
        'usr/share/steamos-manager/remotes.d/50-steamos-arm.toml',
        'etc/inputplumber/devices.d/02-ayn-odin.yaml',
        'etc/inputplumber/devices.d/02-konkr-pocketfit.yaml',
        'etc/inputplumber/devices.d/03-ayaneo-pocket-s2.yaml',
    ]
    remove += [PRIVATE_FW + '/' + name for name in QCA_FIRMWARE]
    upper = 'var/lib/overlays/etc/upper/'
    # KONKR disables Plasma's power button because konkrd owns it. TB520FU
    # masks that daemon, so restore the shared policy in both /etc layers.
    power_policy = REPO / 'steamos-overlay/etc/xdg/powerdevilrc'
    overlay_files['etc/xdg/powerdevilrc'] = power_policy
    overlay_files[upper + 'xdg/powerdevilrc'] = power_policy
    remove += [upper + name.removeprefix('etc/') for name in remove if name.startswith('etc/')]
    user_units = ('konkr-volume.service', 'konkr-focusfix.service',
                  'konkr-android.service', 'konkr-android-setup.service')
    tb_units = ('tb520fu-sns-init.service', 'tb520fu-imu-bridge.service', 'inputplumber.service')
    replace_paths = list(remove) + ['usr/share/easy-ufs-install', 'usr/share/steamos-arm/install-internal']
    replace_paths += [prefix + unit for unit in user_units
                      for prefix in ('etc/systemd/user/', upper + 'systemd/user/')]
    replace_paths += [prefix + unit for unit in MASKED
                      for prefix in ('etc/systemd/system/', upper + 'systemd/system/')]
    replace_paths += [prefix + unit for unit in tb_units for prefix in (
        'usr/lib/systemd/system/multi-user.target.wants/',
        'etc/systemd/system/multi-user.target.wants/', upper + 'systemd/system/multi-user.target.wants/')]
    for name in replace_paths:
        leaf_destination(root, name)
    for name in ('usr/bin/steamos-update', 'usr/share/steamos-arm/tb520fu.json'):
        destination(root, name)
    for name in set(payloads) | set(runtime) | set(overlay_files):
        destination(root, name)
    for name, data in payloads.items():
        write_file(root, name, data)
    for name, (kind, data, mode) in runtime.items():
        dest = destination(root, name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if kind == 'link':
            if dest.exists() or dest.is_symlink(): dest.unlink()
            dest.symlink_to(data)
        else:
            write_file(root, name, data, mode)
    for name, source in overlay_files.items():
        write_file(root, name, source.read_bytes(), source.stat().st_mode & 0o777)
    # Remove only handheld tuning from THIS dedicated image. Repository paths
    # and the rootfs/images of all existing supported devices are untouched.
    for name in remove:
        leaf_destination(root, name).unlink(missing_ok=True)
    for unit in user_units:
        for prefix in ('etc/systemd/user/', 'var/lib/overlays/etc/upper/systemd/user/'):
            path = leaf_destination(root, prefix + unit)
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists() or path.is_symlink(): path.unlink()
            path.symlink_to('/dev/null')
    # /etc is persisted through SteamOS's overlay: mirror masks and config there.
    upper = 'var/lib/overlays/etc/upper/'
    mask_system_services(root, MASKED)
    for unit in tb_units:
        for prefix in ('usr/lib/systemd/system/multi-user.target.wants/',
                       'etc/systemd/system/multi-user.target.wants/',
                       upper + 'systemd/system/multi-user.target.wants/'):
            path = leaf_destination(root, prefix + unit); path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists() or path.is_symlink(): path.unlink()
            path.symlink_to('/usr/lib/systemd/system/' + unit)
    # Generic signed SoC updates carry another kernel and don't know this EFI
    # layout. Block them until a TB520FU-specific update manifest exists.
    updater = b'#!/bin/sh\necho "TB520FU development image: generic SoC updates are unavailable." >&2\nexit 1\n'
    write_file(root, 'usr/bin/steamos-update', updater, 0o755)
    for name in ('usr/share/easy-ufs-install', 'usr/share/steamos-arm/install-internal'):
        path = leaf_destination(root, name)
        if path.is_symlink(): path.unlink()
        elif path.is_dir(): shutil.rmtree(path)
    # Record the dedicated image identity and its source pin.
    write_file(root, 'usr/share/steamos-arm/tb520fu.json', json.dumps({
        'device': 'lenovo,tb520fu', 'source_commit': SOURCE_COMMIT,
        'panels': ['tianma', 'boe'], 'resolution': [2944,1840],
        'refresh_rates': [120], 'linux_verified': False,
    }, indent=2).encode() + b'\n')
    print(f'TB520FU installed: {len(payloads)} firmware/runtime data files; {len(runtime)} built runtime files')

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--firmware', type=Path, required=True)
    ap.add_argument('--check-firmware', action='store_true')
    ap.add_argument('--rootfs', type=Path)
    ap.add_argument('--runtime-stage', type=Path)
    a = ap.parse_args()
    blobs = firmware(a.firmware)
    if a.check_firmware:
        print(f'TB520FU archive verified: {len(blobs)} exact manifest files, sizes and SHA256 hashes')
        return
    if not a.rootfs or not a.runtime_stage:
        ap.error('--rootfs and --runtime-stage required for installation')
    stage = a.runtime_stage.resolve(strict=True)
    runtime = runtime_files(stage)
    install(a.rootfs, blobs, runtime)

if __name__ == '__main__':
    main()
