#!/usr/bin/env python3
"""Inspect compiled TB520FU artifacts without booting or writing a device."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import struct
import subprocess

REPO = Path(__file__).resolve().parents[1]

def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def check(condition, message):
    if not condition: raise ValueError(message)

def elf(path):
    data = path.read_bytes()[:64]
    check(data[:5] == b'\x7fELF\x02' and data[5] == 1 and struct.unpack_from('<H', data, 18)[0] == 183,
          'not an AArch64 ELF: ' + str(path))

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--work', required=True, type=Path)
    ap.add_argument('--rootfs', type=Path)
    ap.add_argument('--output', required=True, type=Path)
    a = ap.parse_args(); work = a.work.resolve(); report = {'device':'TB520FU', 'boot_tested':False}
    pin = dict(line.split('=',1) for line in (REPO/'external-and-mods/tb520fu/source.env').read_text().splitlines() if line.startswith('TB520FU_'))
    kout = (work/'kernel/output/current').resolve(strict=True)
    check((kout/'TB520FU-SOURCE').read_text().strip() == pin['TB520FU_SOURCE_COMMIT'], 'kernel source pin')
    image = kout/'boot/Image'; data = image.read_bytes()
    check(len(data) > 1024**2 and data[56:60] == b'ARMd', 'ARM64 Image header')
    cfg = (kout/('config-'+kout.name)).read_text().splitlines()
    required = ['INITRAMFS_SOURCE', 'DRM_MSM', 'EXT4_FS', 'OVERLAY_FS', 'DEVTMPFS', 'USB_XHCI_HCD', 'USB_DWC3', 'USB_DWC3_QCOM', 'USB_STORAGE', 'NTSYNC', 'TRACING']
    for name in required:
        if name == 'INITRAMFS_SOURCE': check(any(x.startswith('CONFIG_INITRAMFS_SOURCE="/') for x in cfg), 'built-in initramfs missing')
        else: check('CONFIG_'+name+'=y' in cfg, 'early boot config missing: '+name)
    driver_config = {}
    for name in ['DRM_PANEL_NOVATEK_NT36532', 'BACKLIGHT_TB520FU_KTZ8866',
                 'TOUCHSCREEN_NT36532_SPI', 'KEYBOARD_LENOVO_YOGA_SERDEV',
                 'TB520FU_GOODIX_CONTROL', 'INPUT_QCOM_HV_HAPTICS',
                 'SND_SOC_AW882XX', 'SND_SOC_WCD939X_SDW', 'VIDEO_QCOM_IRIS',
                 'ATH12K', 'TYPEC_MUX_PS5169', 'TYPEC_MUX_WCD939X_USBSS',
                 'QCOM_FASTRPC', 'BATTERY_QCOM_BATTMGR']:
        value = next((x.split('=',1)[1] for x in cfg if x.startswith('CONFIG_'+name+'=')), None)
        check(value in ['y','m'], 'TB520FU driver missing: '+name)
        driver_config[name] = value
    for name in ['nt36532-spi.ko','qcom-hv-haptics.ko','tb520fu-goodix.ko',
                 'lenovo-yoga-serdev.ko','snd-soc-aw882xx.ko']:
        check(any((kout/'modules'/kout.name).rglob(name+'*')), 'TB520FU module missing: '+name)
    dtbs = {}
    for name in ['sm8650-lenovo-tb520fu.dtb','sm8650-lenovo-tb520fu-boe.dtb']:
        path = kout/'dtbs'/name; data = path.read_bytes()
        check(data[:4] == b'\xd0\x0d\xfe\xed' and b'lenovo,tb520fu\0' in data, 'incorrect TB520FU DTB: '+name)
        panel = 'boe' if '-boe.' in name else 'tianma'
        check(('lenovo,tb520fu-'+panel+'-nt36532').encode()+b'\0' in data, 'panel compatible mismatch: '+name)
        check(('qcom/sm8650/lenovo/tb520fu/novatek_ts_'+panel+'_fw.bin').encode()+b'\0' in data, 'touch firmware mismatch: '+name)
        dtbs[name] = sha(path)
    modules = list((kout/'modules'/kout.name).rglob('*.ko*'))
    check(len(modules)>10, 'kernel modules missing')
    report['kernel']={'release':kout.name,'source_commit':pin['TB520FU_SOURCE_COMMIT'], 'image_sha256':sha(image),'dtbs':dtbs,'module_count':len(modules),'driver_config':driver_config}
    uefi = work/'uefi/output/tb520fu-uefi-boot.img'; meta = json.loads((uefi.parent/'boot-image.json').read_text())
    lock = json.loads((REPO/'external-and-mods/tb520fu/uefi/source-lock.json').read_text())
    check(meta['compiled'] is True and meta['device']=='TB520FU' and meta['mu_commit']==lock['mu_commit'] and meta['stock_inputs']==lock['stock'], 'UEFI source provenance')
    check(sha(uefi)==meta['sha256'], 'UEFI hash mismatch')
    data=uefi.read_bytes()
    check(data[:8]==b'ANDROID!' and struct.unpack_from('<I',data,40)[0]==4 and struct.unpack_from('<I',data,20)[0]==1584, 'stock-compatible Android v4 header')
    size=struct.unpack_from('<I',data,8)[0]; payload=data[4096:4096+size]
    # BootShim and its compiled FV are gzip-packed by Mu's pinned builder.
    if payload[:2]==b'\x1f\x8b': payload=gzip.decompress(payload)
    check(payload[56:60]==b'ARMd' and b'_FVH' in payload, 'UEFI BootShim/FV missing')
    report['uefi']=meta
    if a.rootfs:
        root=a.rootfs.resolve(); check((root/'.tb520fu-rootfs').is_file(),'rootfs ownership marker')
        identity=json.loads((root/'usr/share/steamos-arm/tb520fu.json').read_text())
        check(identity['source_commit']==pin['TB520FU_SOURCE_COMMIT'] and identity['panels']==['tianma','boe'], 'rootfs TB520FU identity')
        files=['usr/bin/bash','usr/bin/inputplumber','usr/bin/hexagonrpcd','usr/libexec/tb321fu-imu-bridge','usr/libexec/iio-sensor-proxy']
        for name in files: elf(root/name)
        modroot=root/'usr/lib/modules'; check([d.name for d in modroot.iterdir() if d.is_dir()]==[kout.name], 'foreign or missing rootfs kernel modules')
        for name in files[1:]:
            result=subprocess.run(['chroot',str(root),'/usr/bin/ldd','/'+name],check=True,capture_output=True,text=True)
            check('not found' not in result.stdout, 'missing runtime dependency: '+name)
        report['rootfs']={'identity':identity,'executables':{name:sha(root/name) for name in files},
                          'common_base':json.loads((root/'opt/tb520fu-base-release.json').read_text()) if (root/'opt/tb520fu-base-release.json').exists() else None,
                          'runtime_manifest_sha256':sha(root/'opt/tb520fu-runtime-stage/TB520FU-RUNTIME.json')}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,indent=2)+'\n')
    print('Compiled artifacts inspected:',a.output)

if __name__=='__main__': main()
