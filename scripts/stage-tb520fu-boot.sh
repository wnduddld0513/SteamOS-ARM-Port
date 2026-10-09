#!/usr/bin/env bash
# stage-tb520fu-boot.sh BOOT_DIR KERNEL_OUT tianma|boe|both CMDLINE
# EFI media preparation only. No flashing of boot, ABL or internal partitions.
set -euo pipefail
source "$(dirname "$0")/tb520fu-common.sh"
boot="${1:?BOOT_DIR}" kout="$(realpath -e "${2:?KERNEL_OUT}")"
panel="${3:?tianma|boe|both}" cmdline="${4:?CMDLINE}"
[[ -d "$boot" && -s "$kout/boot/Image" ]] || tb520fu_die "missing boot directory/Image"
[[ "$(cat "$kout/TB520FU-SOURCE")" == "$TB520FU_SOURCE_COMMIT" ]] || tb520fu_die "kernel source pin mismatch"
case "$panel" in tianma|boe) panels=("$panel");; both) panels=(tianma boe);; *) tb520fu_die "invalid panel";; esac
[[ "$cmdline" == *root=UUID=* && "$cmdline" != *PARTLABEL=STORAGE* ]] || tb520fu_die "external image root UUID required"
cache="${STEAMOS_WORK:-/work/tb520fu}/cache/grub"; mkdir -p "$cache"
get() {
    local name="$1" sha="$2" dest="$3"
    if [[ ! -f "$cache/$name" ]] || ! echo "$sha  $cache/$name" | sha256sum -c --quiet; then
        curl -fL --retry 3 "$TB520FU_GRUB_URL/$name" -o "$cache/$name.part"
        echo "$sha  $cache/$name.part" | sha256sum -c --quiet
        mv "$cache/$name.part" "$cache/$name"
    fi
    install -Dm0644 "$cache/$name" "$dest"
}
mkdir -p "$boot/dtb" "$boot/tablet"
get BOOTAA64.EFI "$TB520FU_GRUB_SHA256" "$boot/EFI/BOOT/BOOTAA64.EFI"
get QCOMRAMP-CONFIGFILE.EFI "$TB520FU_QCOMRAMP_SHA256" "$boot/EFI/BOOT/QCOMRAMP.EFI"
install -m0644 "$kout/boot/Image" "$boot/Image"
marker="steamos-tb520fu-$(od -An -N8 -tx1 /dev/urandom | tr -d ' \n')"
printf 'TB520FU external boot media\n' > "$boot/$marker"
cat > "$boot/EFI/BOOT/grub.cfg" <<CFG
set timeout=2
set default=0
menuentry "SteamOS ARM TB520FU" {
    search --no-floppy --file /$marker --set=root
    chainloader /EFI/BOOT/QCOMRAMP.EFI
    boot
}
menuentry "Reboot" { reboot }
menuentry "Power off" { halt }
CFG
{
    printf 'set timeout=8\nset default=0\n'
    for p in "${panels[@]}"; do
        dtb=sm8650-lenovo-tb520fu.dtb
        [[ "$p" != boe ]] || dtb=sm8650-lenovo-tb520fu-boe.dtb
        [[ -s "$kout/dtbs/$dtb" ]] || tb520fu_die "missing $dtb"
        install -m0644 "$kout/dtbs/$dtb" "$boot/dtb/$dtb"
        cat <<CFG
menuentry "SteamOS ARM TB520FU ($p panel)" {
    search --no-floppy --file /$marker --set=root
    devicetree /dtb/$dtb
    qcomfdtmem source rampartition
    linuxdirect /Image $cmdline
}
CFG
    done
} > "$boot/EFI/BOOT/qcomramp.cfg"
# Prefer our TB520FU Mu output with provenance; an explicitly supplied TB520FU
# image also needs an exact SHA256. No device-specific image is downloaded.
uefi="${TB520FU_UEFI_BOOT_IMG:-}"
uefi_sha="${TB520FU_UEFI_SHA256:-}"
if [[ -z "$uefi" ]]; then
    uefi_dir="${STEAMOS_WORK:-/work/tb520fu}/uefi/output"
    uefi="$uefi_dir/tb520fu-uefi-boot.img"
    uefi_sha="$(python3 - "$uefi_dir/boot-image.json" "$TB520FU_REPO_ROOT/external-and-mods/tb520fu/uefi/source-lock.json" <<'PY'
import json, sys
meta = json.load(open(sys.argv[1])); lock = json.load(open(sys.argv[2]))
assert meta['device'] == 'TB520FU' and meta['mu_commit'] == lock['mu_commit']
assert meta['stock_inputs'] == lock['stock'] and meta['compiled'] is True
print(meta['sha256'])
PY
)" || tb520fu_die "build the TB520FU UEFI or supply a TB520FU image and its SHA256"
    install -m0644 "$uefi_dir/boot-image.json" "$boot/tablet/uefi-boot-image.json"
fi
[[ "$uefi_sha" =~ ^[a-f0-9]{64}$ && -s "$uefi" ]] || tb520fu_die "TB520FU UEFI image and SHA256 required"
echo "$uefi_sha  $uefi" | sha256sum -c --quiet
install -m0644 "$uefi" "$boot/tablet/tb520fu-uefi-boot.img"
cat > "$boot/tablet/README.txt" <<'TXT'
TB520FU development boot files. Linux boot has not been tested.
The included TB520FU UEFI is experimental; a successful boot is not verified.
No Y700 boot image or ROCKNIX ABL is included. Do not flash boot/KERNEL.
The firmware must expose this USB drive to UEFI/GRUB. Both panels are menu entries.
No internal-storage installation or automatic GPT/slot writes are enabled.
TXT
(cd "$boot" && sha256sum Image dtb/*.dtb EFI/BOOT/*.EFI tablet/tb520fu-uefi-boot.img > TB520FU-SHA256SUMS)
