#!/usr/bin/env python3
"""Static checks only: no make, compiler, dtc, m4, alsatplg or image creation."""
import argparse
import ast
import importlib.util
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]
BASE = '4673fa6bfc8b6a598ef799ed0e88f98a9b045285'
PIN = 'fcf8cd2513b429fa54ac418c33ced27d1ed0815e'

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--kconfig-tree', type=Path)
    ap.add_argument('--uefi-prepared', type=Path)
    a=ap.parse_args()
    # Git applies .gitattributes line-ending filters; compare repository contents.
    files=subprocess.check_output(['git','ls-tree','-r','--name-only',BASE],cwd=ROOT,text=True).splitlines()
    changed=set(subprocess.check_output(['git','diff','--name-only',BASE],cwd=ROOT,text=True).splitlines())
    forbidden=changed.intersection(files)-{'README.md','.gitignore'}
    assert not forbidden, 'original files changed: '+str(sorted(forbidden))
    preserved=len(files)-2
    print(f'Existing Git file contents preserved: {preserved}')
    scripts=[ROOT/'make-steamos-tb520fu.sh', *ROOT.glob('scripts/*tb520fu*.sh'),
             ROOT/'tools/setup-fork.sh',ROOT/'.githooks/pre-push',
             ROOT/'external-and-mods/tb520fu/initramfs/init']
    for p in scripts:
        subprocess.run(['bash','-n',str(p)],check=True)
        for body in re.findall(r"<<'PY'\n(.*?)\nPY(?:\n|$)", p.read_text(), re.S): ast.parse(body)
    for p in [*ROOT.glob('scripts/*tb520fu*.py'), *ROOT.glob('tools/*tb520fu*.py'),
              *ROOT.glob('external-and-mods/tb520fu/uefi/Platforms/**/*.py')]: ast.parse(p.read_text())
    for folder in (ROOT/'tb520fu-overlay', ROOT/'external-and-mods/tb520fu/uefi'):
        for p in folder.rglob('*.toml'): tomllib.loads(p.read_text())
    for p in (ROOT/'external-and-mods/tb520fu/uefi').rglob('*.json'): json.loads(p.read_text())
    uefi=json.loads((ROOT/'external-and-mods/tb520fu/uefi/stock-inventory.json').read_text())
    assert len(uefi['stock_modules']) == 73 and len(uefi['memory_regions']) == 43
    usb = {e['name']: e for e in uefi['stock_modules']}
    for name in ('UsbBusDxe', 'UsbMassStorageDxe', 'UsbConfigDxe'):
        assert name in usb and name not in uefi['standard_source_services']
        assert not usb[name].get('binary_patch'), name
    assert uefi['compile_performed'] is False and uefi['boot_tested'] is False
    mem={m['name']: m for m in uefi['memory_regions']}
    assert mem['FD Reserved']['address'] == 0xA7000000 and mem['FD Reserved']['length'] == 0x100000
    assert mem['UEFI_FD']['address'] == 0xA7100000 and mem['UEFI_FD']['length'] == 0x300000
    assert mem['UEFI_Stack']['address'] == 0xA760D000
    assert mem['Display_Reserved']['address'] == 0xD5100000
    assert mem['TB520FU_Ramoops']['address'] == 0xA2000000
    assert mem['TB520FU_Ramoops']['length'] == 0x200000
    assert mem['TB520FU_Ramoops']['cache'] == 'UNCACHED_UNBUFFERED_XN'
    assert mem['TB520FU_Ramoops']['resource_type'] == 0
    assert mem['TB520FU_Ramoops']['memory_type'] == 0
    assert not any(e['name'] == 'DisplayDxe' for e in uefi['stock_modules'])
    assert uefi['standard_source_services']['DisplayDxe'].endswith('/SimpleFbDxe.inf')
    # Rootfs tuning and UEFI are new opt-in paths; no existing builder references them.
    for p in ('make-steamos-sm8350.sh','make-steamos-sm8650.sh','make-steamos-sm8750.sh','scripts/apply-overlays.sh'):
        assert 'tb520fu' not in (ROOT/p).read_text().lower()

    env=(ROOT/'external-and-mods/tb520fu/source.env').read_text()
    assert 'TB520FU_SOURCE_COMMIT='+PIN in env
    manifest=json.loads((ROOT/'external-and-mods/tb520fu/firmware-manifest.json').read_text())['files']
    assert len(manifest)==274
    for name in ('novatek_ts_tianma_fw.bin','novatek_ts_boe_fw.bin'): assert name in manifest
    spec=importlib.util.spec_from_file_location('tb520fu_installer',ROOT/'scripts/install-tb520fu.py')
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    assert module.SOURCE_COMMIT==PIN
    assert 'TB520FU_FIRMWARE_SHA256='+module.FIRMWARE_SHA in env
    # Exercise the installer against temporary fixtures, never a real rootfs.
    with tempfile.TemporaryDirectory(prefix='tb520fu-static-') as td:
        temp=Path(td); r=temp/'rootfs'; r.mkdir(); (r/'usr/bin').mkdir(parents=True)
        (r/'usr/bin/bash').write_bytes(b'fixture')
        try: module.install(r,{},{}); raise AssertionError('foreign rootfs accepted')
        except ValueError: pass
        (r/'.tb520fu-rootfs').write_text('fixture')
        sentinel=r/'usr/lib/firmware/ath12k/WCN7850/hw2.0/amss.bin'
        sentinel.parent.mkdir(parents=True); sentinel.write_bytes(b'other-device-firmware')
        blobs={module.PRIVATE_FW+'/qcom/sm8650/lenovo/tb520fu/test.bin':b'tb520fu'}
        module.install(r,blobs,{})
        module.install(r,blobs,{})
        assert sentinel.read_bytes()==b'other-device-firmware'
        assert (r/'etc/systemd/system/konkrd.service').readlink()==Path('/dev/null')
        assert (r/'usr/lib/systemd/user/gamescope-session.service.d/90-tb520fu.conf').is_file()
        assert (r/'usr/share/steamos-arm/tb520fu.json').is_file()
        # An escaping existing symlink must fail before firmware is written.
        bad=temp/'bad'; (bad/'usr/bin').mkdir(parents=True)
        (bad/'usr/bin/bash').write_bytes(b'fixture');(bad/'.tb520fu-rootfs').touch()
        outside=temp/'outside';outside.mkdir();(bad/'usr/lib').symlink_to(outside)
        try: module.install(bad,blobs,{}); raise AssertionError('escaping symlink accepted')
        except ValueError: pass
        assert not list(outside.iterdir())
        bad2=temp/'bad-etc'; (bad2/'usr/bin').mkdir(parents=True)
        (bad2/'usr/bin/bash').write_bytes(b'fixture'); (bad2/'.tb520fu-rootfs').touch()
        (bad2/'etc').symlink_to(outside)
        try: module.install(bad2,blobs,{}); raise AssertionError('escaping etc symlink accepted')
        except ValueError: pass
        assert not list(outside.iterdir())
        assert not (bad2/'usr/lib/firmware').exists()

    if a.kconfig_tree:
        symbols=set()
        for p in a.kconfig_tree.rglob('Kconfig*'):
            if p.is_file():
                symbols.update(re.findall(r'^\s*(?:menu)?config\s+(\w+)',p.read_text(errors='replace'),re.M))
        text=(ROOT/'scripts/build-tb520fu-kernel.sh').read_text()+(ROOT/'external-and-mods/kernel-common/steamos.config').read_text()
        requested=set(re.findall(r'CONFIG_([A-Z0-9_]+)=',text))
        missing=requested-symbols
        assert not missing, 'unknown additional Kconfig symbols: '+str(sorted(missing))
        print(f'Additional Kconfig symbols exist: {len(requested)}; dependency resolution not run')
    if a.uefi_prepared:
        mu=a.uefi_prepared.resolve()
        lock=json.loads((ROOT/'external-and-mods/tb520fu/uefi/source-lock.json').read_text())
        assert subprocess.check_output(['git','-C',str(mu),'rev-parse','HEAD'],text=True).strip() == lock['mu_commit']
        for patch_name in ('dxe-dispatch-trace.patch', 'gic-unhandled-irq.patch', 'spmi-abort-recovery.patch', 'usb-storage-retry.patch'):
            subprocess.run(['git', '-C', str(mu), 'apply', '--ignore-whitespace',
                            '--reverse', '--check',
                            str(ROOT/'external-and-mods/tb520fu/uefi/patches'/patch_name)], check=True)
        assert (mu/'Mu_Basecore/UefiCpuPkg/Library/CpuExceptionHandlerLib/AArch64/Tb520fuSpmiRecovery.h').read_bytes() == (ROOT/'external-and-mods/tb520fu/uefi/patches/spmi-abort-recovery.h').read_bytes()
        assert (mu/'Common/Mu/PcBdsPkg/MsBootPolicy/Tb520fuUsbDiagnostics.h').read_bytes() == (ROOT/'external-and-mods/tb520fu/uefi/patches/usb-storage-diagnostics.h').read_bytes()
        actual=json.loads((mu/'TB520FU-PREPARED.json').read_text())
        assert actual == uefi
        for entry in actual['stock_modules']:
            name=entry['name']
            if 'pe_sha256' in entry:
                pe=mu/'Binaries/tb520fu'/name/(name+'.efi')
                assert hashlib.sha256(pe.read_bytes()).hexdigest()==entry['pe_sha256']
                if entry['depex_sha256']:
                    dep=mu/'Binaries/tb520fu'/name/(name+'.depex')
                    assert hashlib.sha256(dep.read_bytes()).hexdigest()==entry['depex_sha256']
            else:
                raw=mu/'Binaries/tb520fu/RawFiles'/name
                assert hashlib.sha256(raw.read_bytes()).hexdigest()==entry['raw_sha256']
        template=ROOT/'external-and-mods/tb520fu/uefi/Platforms/Lenovo/tb520fuPkg'
        for src in template.rglob('*'):
            if src.is_file() and '__pycache__' not in src.parts:
                assert src.read_bytes() == (mu/'Platforms/Lenovo/tb520fuPkg'/src.relative_to(template)).read_bytes(), str(src)
        assert (mu/'Resources/Configs/tb520fu.toml').read_bytes() == (ROOT/'external-and-mods/tb520fu/uefi/Resources/Configs/tb520fu.toml').read_bytes()
        print('Prepared UEFI source: 73 module/raw hashes, DEPEX, 43 memory regions and all platform source files match')
    # Exercise push restrictions without contacting or mutating any Git remote.
    hook=ROOT/'.githooks/pre-push'
    refs='refs/heads/tb520fu '+('1'*40)+' refs/heads/tb520fu '+('0'*40)+'\n'
    for remote, data, accepted in (
        ('https://github.com/wnduddld0513/SteamOS-ARM-Port.git',refs,True),
        ('https://github.com/hashtagbasit/SteamOS-ARM-Port.git',refs,False),
        ('https://github.com/wnduddld0513/SteamOS-ARM-Port.git',refs.replace('refs/heads/tb520fu','refs/heads/main'),False)):
        result=subprocess.run(['sh',str(hook),'origin',remote],input=data,text=True,capture_output=True)
        assert (result.returncode == 0) == accepted
    print(f'Shell syntax: {len(scripts)} scripts; Python/TOML/JSON parsed; installer isolation/idempotence passed')
    print('This static checker invokes no compiler or device boot; inspect compiled artifacts separately.')

if __name__=='__main__': main()
