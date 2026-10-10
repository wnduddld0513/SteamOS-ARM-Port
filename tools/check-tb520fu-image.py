#!/usr/bin/env python3
"""Read-only inspection of a generated TB520FU USB image; no device writes."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


def check(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--work', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    a = ap.parse_args()
    work = a.work.resolve(strict=True)
    image = work / 'steamos-tb520fu.img'
    check(image.is_file() and not image.is_symlink(), 'regular generated image required')
    check((work/'rootfs/.tb520fu-rootfs').is_file(), 'dedicated build marker missing')
    table = json.loads(run('sfdisk', '--json', str(image)))['partitiontable']
    parts = table['partitions']
    check(table['label']=='dos' and [p['type'] for p in parts]==['c','83','83'], 'USB layout mismatch')
    loop = run('losetup', '--read-only', '--find', '--show', '--partscan', str(image)).strip()
    mounts = []
    tmp = tempfile.mkdtemp(prefix='tb520fu-image-check-')
    try:
        devices = [loop+'p'+str(i) for i in [1,2,3]]
        for i, dev in enumerate(devices):
            tool = 'fsck.vfat' if i==0 else 'e2fsck'
            result = subprocess.run([tool,'-n',dev],capture_output=True,text=True)
            check(result.returncode==0, 'filesystem check failed: '+dev+' '+result.stdout+result.stderr)
        root = Path(tmp)/'root'; boot=Path(tmp)/'boot'
        for dest, dev, opts in [(root,devices[1],'ro,noload'),(boot,devices[0],'ro')]:
            dest.mkdir()
            run('mount','-o',opts,dev,str(dest)); mounts.append(dest)
        uuid=run('blkid','-s','UUID','-o','value',devices[1]).strip()
        grub=(boot/'EFI/BOOT/qcomramp.cfg').read_text()
        loader=(boot/'EFI/BOOT/grub.cfg').read_text()
        check('chainloader /EFI/BOOT/QCOMRAMP.EFI' in loader, 'QCOMRAMP chainloader missing')
        check('root=UUID='+uuid in grub,'GRUB root UUID mismatch')
        for dtb in ['sm8650-lenovo-tb520fu.dtb','sm8650-lenovo-tb520fu-boe.dtb']:
            check(dtb in grub,'panel menu missing: '+dtb)
            local=work/'kernel/output/current/dtbs'/dtb
            candidates=list(boot.rglob(dtb))
            check(len(candidates)==1 and sha(candidates[0])==sha(local),'DTB hash mismatch')
        check(sha(boot/'tablet/tb520fu-uefi-boot.img')==sha(work/'uefi/output/tb520fu-uefi-boot.img'),'UEFI image mismatch')
        candidates=list(boot.rglob('Image'))
        check(len(candidates)==1 and sha(candidates[0])==sha(work/'kernel/output/current/boot/Image'),'kernel hash mismatch')
        fstab=(root/'etc/fstab').read_text()
        check('UUID='+uuid in fstab and fstab==(root/'var/lib/overlays/etc/upper/fstab').read_text(),'fstab layers mismatch')
        identity=json.loads((root/'usr/share/steamos-arm/tb520fu.json').read_text())
        check(identity['panels']==['tianma','boe'],'both panel support missing')
        check((root/'etc/machine-id').stat().st_size==0,'machine-id must be generated at first boot')
        for name in ['opt/tb520fu-build','opt/tb520fu-runtime-stage','root/.cargo','var/cache/pacman/pkg']:
            folder=root/name
            check(not folder.exists() or not any(folder.iterdir()), 'build cache leaked: '+name)
        report={'device':'TB520FU','boot_tested':False,'image':image.name,'bytes':image.stat().st_size,
                'sha256':sha(image),'root_uuid':uuid,'partition_table':table,'identity':identity,
                'checks':['all three filesystems clean (read-only check)','two panel DTBs match','Image and UEFI hashes match',
                          'GRUB and both fstab layers select root UUID','empty machine-id','build caches excluded']}
        a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.write_text(json.dumps(report,indent=2)+'\n')
        print('USB image inspected:',a.output)
    finally:
        for dest in reversed(mounts):
            subprocess.run(['umount',str(dest)],check=True)
        subprocess.run(['losetup','-d',loop],check=True)
        for child in Path(tmp).iterdir():
            child.rmdir()
        Path(tmp).rmdir()


if __name__=='__main__':
    main()
