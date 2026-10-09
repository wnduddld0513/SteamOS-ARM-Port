#!/usr/bin/env bash
# Explicit future build entry point. Never called by static checks.
set -euo pipefail
source "$(dirname "$0")/tb520fu-common.sh"
work="${STEAMOS_WORK:-/work/tb520fu}/kernel"
mkdir -p "$work"
source_repo="$(tb520fu_source)"
exported="$(mktemp -d "$work/source.XXXXXX")"
trap 'rm -rf -- "$exported"' EXIT
tb520fu_export "$source_repo" "$exported" packages/kernel
pkg="$exported/packages/kernel"
[[ "$(sed -n 's/^VERSION=//p' "$pkg/BASE.env")" == "$TB520FU_KERNEL_VERSION" ]] ||
    tb520fu_die "kernel version differs from source lock"
# Keep the full TB520FU patch series; do not mix ROCKNIX/Y700 patch sets.
cat "$TB520FU_REPO_ROOT/external-and-mods/kernel-common/steamos.config" >> "$pkg/config/armada-kernel.config.overrides"
printf '\nCONFIG_LOCALVERSION="-tb520fu-steamos"\nCONFIG_LOCALVERSION_AUTO=n\n' >> "$pkg/config/armada-kernel.config.overrides"
bb="${TB520FU_BUSYBOX:-/bin/busybox}"
[[ -f "$bb" ]] || tb520fu_die "TB520FU_BUSYBOX must name a static ARM64 BusyBox"
readelf -h "$bb" | grep -q 'Machine:.*AArch64' || tb520fu_die "BusyBox is not ARM64"
if readelf -l "$bb" | grep -q INTERP; then tb520fu_die "BusyBox must be static"; fi
strings "$bb" | grep findfs >/dev/null || tb520fu_die "BusyBox lacks findfs"
ird="$work/initramfs"; mkdir -p "$ird/bin" "$ird/dev" "$ird/proc" "$ird/sys" "$ird/newroot"
install -m0755 "$bb" "$ird/bin/busybox"
install -m0755 "$TB520FU_REPO_ROOT/external-and-mods/tb520fu/initramfs/init" "$ird/init"
printf 'CONFIG_INITRAMFS_SOURCE="%s"\nCONFIG_INITRAMFS_ROOT_UID=0\nCONFIG_INITRAMFS_ROOT_GID=0\nCONFIG_BLK_DEV_INITRD=y\nCONFIG_RD_GZIP=y\nCONFIG_DEVTMPFS=y\nCONFIG_DEVTMPFS_MOUNT=y\nCONFIG_OVERLAY_FS=y\nCONFIG_EXT4_FS=y\nCONFIG_SCSI=y\nCONFIG_BLK_DEV_SD=y\nCONFIG_USB=y\nCONFIG_USB_XHCI_HCD=y\nCONFIG_USB_XHCI_PLATFORM=y\nCONFIG_USB_DWC3=y\nCONFIG_USB_DWC3_QCOM=y\nCONFIG_USB_DWC3_DUAL_ROLE=y\nCONFIG_USB_STORAGE=y\nCONFIG_USB_UAS=y\n' "$ird" >> "$pkg/config/armada-kernel.config.overrides"
# DRM_MSM is built in and probes before switching root. Put its exact stock
# microcode and both touch variants in the initramfs as well as the rootfs.
python3 - "$TB520FU_REPO_ROOT/scripts/install-tb520fu.py" \
    "${TB520FU_FIRMWARE:-$TB520FU_REPO_ROOT/external-and-mods/tb520fu/local/firmware-lenovo-tb520fu.tar.gz}" "$ird" <<'PY'
import importlib.util, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location('tb520fu_fw', sys.argv[1])
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
blobs = module.firmware(Path(sys.argv[2]))
names = {'gen70900_sqe.fw', 'gmu_gen70900.bin', 'gen70900_zap.mbn',
         'novatek_ts_tianma_fw.bin', 'novatek_ts_boe_fw.bin'}
found = set()
for name, data in blobs.items():
    if Path(name).name in names:
        target = Path(sys.argv[3]) / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data); found.add(target.name)
assert found == names, 'missing early display/touch firmware'
PY
# Keep NTSYNC built in as required by the pinned kernel recipe. Normalize the
# merged fragment so its strict =y check sees only effective final assignments.
printf '\nCONFIG_NTSYNC=y\n' >> "$pkg/config/armada-kernel.config.overrides"
python3 - "$pkg/config/armada-kernel.config.overrides" <<'PY'
import re, sys
from pathlib import Path
path = Path(sys.argv[1])
lines = path.read_text().splitlines()
keys = [re.match(r"(?:# )?(CONFIG_[A-Za-z0-9_]+)(?:=| is not set$)", line) for line in lines]
last = {match[1]: i for i, match in enumerate(keys) if match}
path.write_text("\n".join(line for i, (line, match) in enumerate(zip(lines, keys))
                           if not match or last[match[1]] == i) + "\n")
PY
# FAST could silently reuse another kernel configuration.
env -u FAST KERNEL_VERSION="$TB520FU_KERNEL_VERSION" WORK_DIR="$work/build" OUT_DIR="$work/archives" \
    bash "$pkg/scripts/build-kernel.sh"
release="${TB520FU_KERNEL_VERSION}-tb520fu-steamos"
archive="$work/archives/armada-kernel-${release}.tar.zst"
[[ -f "$archive" ]] || tb520fu_die "expected output missing: $archive"
(cd "$work/archives" && sha256sum -c "${archive##*/}.sha256")
out="$work/output/$release"; mkdir -p "$out/boot" "$out/modules" "$out/dtbs" "$out/firmware"
stage="$(mktemp -d "$work/unpack.XXXXXX")"
trap 'rm -rf -- "$exported" "$stage"' EXIT
tar --zstd -xf "$archive" -C "$stage"
[[ ! -e "$out/modules/$release" ]] || tb520fu_die "output already exists; use a fresh STEAMOS_WORK"
cp -a "$stage/lib/modules/$release" "$out/modules/$release"
cp "$out/modules/$release/vmlinuz" "$out/boot/Image"
cp "$out/modules/$release/dtb/qcom/"sm8650-lenovo-tb520fu*.dtb "$out/dtbs/"
cp "$work/build/linux-$TB520FU_KERNEL_VERSION/.config" "$out/config-$release"
# Compatibility carrier for the rootfs installer, NOT a Lenovo boot image.
python3 "$TB520FU_REPO_ROOT/external-and-mods/kernel-common/mkbootimg-v0.py" \
    --kernel "$out/boot/Image" --out "$out/boot/KERNEL"
(cd "$out/boot" && md5sum KERNEL > KERNEL.md5)
printf '%s\n' "$TB520FU_SOURCE_COMMIT" > "$out/TB520FU-SOURCE"
ln -sfn "$release" "$work/output/current"
echo "TB520FU kernel prepared: $out (stage-tb520fu-boot.sh provides EFI boot files)"
