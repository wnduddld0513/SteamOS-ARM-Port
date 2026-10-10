#!/usr/bin/env bash
# Opt-in TB520FU external image recipe. Existing per-SoC builders are unchanged.
# This is an untested development image, requiring a TB520FU-compatible UEFI.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS="${ROOT}/scripts"
# Rootfs, mounts and image must live on a Linux filesystem (not exFAT).
WORKDIR="${STEAMOS_WORK:-/work/tb520fu}"
export STEAMOS_WORK="$WORKDIR"
R="${STEAMOS_ROOTFS:-${WORKDIR}/rootfs}"
MOD="${ROOT}/external-and-mods"
OVL="${ROOT}/steamos-overlay"
SOC=sm8650
export SOC
KOUT="${TB520FU_KERNEL_OUT:-${WORKDIR}/kernel/output/current}"
source "${SCRIPTS}/tb520fu-common.sh"
BOX64_SRC="${BOX64_SRC:-${MOD}/BOX64/box64}"
BOX64_BUILD="${BOX64_BUILD:-${WORKDIR}/box64-build}"
export BOX64_BUILD
IMG="${STEAMOS_TB520FU_IMG:-${WORKDIR}/steamos-tb520fu.img}"
MNT="${WORKDIR}/.image-mnt"
LOOPDEV=""

BOOT_MIB="${BOOT_MIB:-512}"
# Empty ROOT_MIB / HOME_MIB → pack-time size. Home grows to the card on first boot.
AUTO_ROOT=0
if [[ -z "${ROOT_MIB:-}" ]]; then
  AUTO_ROOT=1
  ROOT_MIB=16384
fi
AUTO_HOME=0
if [[ -z "${HOME_MIB:-}" ]]; then
  AUTO_HOME=1
  HOME_MIB=1024
fi

SKIP_DOWNLOAD=0
SKIP_APPLY=0
SKIP_BOX64=0
IMAGE_ONLY=0
PREPARE_ROOTFS_ONLY=0
BASE_RELEASE=0

log() { printf '==> %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

sudo_run() {
  if [[ "${EUID}" -eq 0 ]]; then
    "$@"
    return
  fi
  if sudo -n true 2>/dev/null; then
    sudo "$@"
    return
  fi
  printf 'steam\n' | sudo -S -p '' "$@"
}

usage() {
  cat <<EOF
Usage: $0 [options]

  --base-release    Import pinned common SM8650 userspace, then build TB520FU runtime/image
  --skip-download   Reuse existing official rootfs/ chunks
  --skip-apply      Do not re-run scripts/apply-overlays.sh
  --skip-box64      Do not rebuild Box64
  --prepare-rootfs  Prepare the dedicated rootfs, then stop before TB520FU runtime/image creation
  --image-only      Pack from the prepared TB520FU rootfs and runtime stage
  --img PATH        Output image (default: ${IMG})

Env: STEAMOS_WORK STEAMOS_ROOTFS STEAMOS_TB520FU_IMG TB520FU_KERNEL_OUT
     TB520FU_FIRMWARE TB520FU_RUNTIME_STAGE TB520FU_PANEL (tianma|boe|both)
     TB520FU_UEFI_BOOT_IMG TB520FU_UEFI_SHA256 (optional explicit UEFI override)
     empty ROOT_MIB/HOME_MIB = auto (tight pack; home grows on first boot)
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --base-release) BASE_RELEASE=1; SKIP_APPLY=1; SKIP_BOX64=1 ;;
    --prepare-rootfs) PREPARE_ROOTFS_ONLY=1 ;;
    --skip-download) SKIP_DOWNLOAD=1 ;;
    --skip-apply) SKIP_APPLY=1 ;;
    --skip-box64) SKIP_BOX64=1 ;;
    --image-only) IMAGE_ONLY=1; SKIP_DOWNLOAD=1; SKIP_APPLY=1; SKIP_BOX64=1 ;;
    --img) IMG="$2"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
  shift
done

KOUT="$(realpath -e "$KOUT")"
[[ "$(cat "$KOUT/TB520FU-SOURCE")" == "$TB520FU_SOURCE_COMMIT" ]] || tb520fu_die "wrong TB520FU kernel source pin"
export KERNEL_OUT="$KOUT"
# Reject the host filesystem and a rootfs belonging to another device.
R="$(realpath -m "$R")"
[[ "$R" != / && "$R" != /work/rootfs ]] || die "dedicated TB520FU rootfs required"
if [[ -d "$R" && ! -f "$R/.tb520fu-rootfs" ]] && [[ -n "$(ls -A "$R")" ]]; then
  die "rootfs already exists without the TB520FU ownership marker; use a fresh path"
fi
mkdir -p "$R" "$WORKDIR"
printf 'TB520FU dedicated development rootfs\n' > "$R/.tb520fu-rootfs"
export STEAMOS_ROOTFS="$R"
if [[ "$BASE_RELEASE" == 1 ]]; then
  sudo_run python3 "$SCRIPTS/import-tb520fu-rootfs.py" "$R" --cache "$WORKDIR/base-release"
fi
STEAMOS_BUILD="${STEAMOS_BUILD:-20261002.6232440}"
STEAMOS_BUNDLE="deckard-${STEAMOS_BUILD}-${STEAMOS_VERSION:-0.5.3}"
STEAMOS_URL="https://steamdeck-images.steamos.cloud/vr/${STEAMOS_BUILD}"

ensure_official_rootfs() {
  if [[ -x "${R}/usr/bin/bash" ]]; then
    log "Official rootfs already extracted"
    return 0
  fi
  [[ "$SKIP_DOWNLOAD" -eq 1 ]] && die "rootfs missing and --skip-download set"
  command -v unsquashfs >/dev/null || die "unsquashfs missing (apt install squashfs-tools)"
  local dl="${WORKDIR}/steamos-${STEAMOS_BUILD}" img sha
  mkdir -p "${dl}"
  img="${dl}/rootfs.img"
  if [[ ! -s "${dl}/bundle/rootfs.img.caibx" ]]; then
    log "Fetching RAUC bundle ${STEAMOS_BUNDLE}"
    curl -fL -o "${dl}/${STEAMOS_BUNDLE}.raucb" "${STEAMOS_URL}/${STEAMOS_BUNDLE}.raucb"
    rm -rf "${dl}/bundle"
    unsquashfs -q -d "${dl}/bundle" "${dl}/${STEAMOS_BUNDLE}.raucb"
  fi
  sha="$(sed -n '/^\[image.rootfs\]/,/^\[/{s/^sha256=//p}' "${dl}/bundle/manifest.raucm")"
  if [[ ! -s "${img}" || ! -f "${img}.ok" ]]; then
    log "Assembling official rootfs.img from casync chunks (sha256 ${sha})"
    python3 "${SCRIPTS}/extract_rootfs.py" \
      --caibx "${dl}/bundle/rootfs.img.caibx" --output "${img}" \
      --store "${STEAMOS_URL}/${STEAMOS_BUNDLE}.castr" \
      --store "https://steamdeck-images.steamos.cloud/vr/chunks.castr" \
      --expected-sha256 "${sha}"
    touch "${img}.ok"
  fi
  log "Unpacking rootfs.img → ${R}"
  mkdir -p "${WORKDIR}/.rootfs-ro" "${R}"
  sudo_run mount -o loop,ro "${img}" "${WORKDIR}/.rootfs-ro"
  sudo_run rsync -aHAX --filter="-x btrfs.*" --numeric-ids "${WORKDIR}/.rootfs-ro/" "${R}/"
  sudo_run umount "${WORKDIR}/.rootfs-ro"
  [[ -x "${R}/usr/bin/bash" ]] || die "unpacked rootfs has no /usr/bin/bash"
}

apply_mods() {
  [[ "$SKIP_APPLY" -eq 1 ]] && { log "Skipping apply-overlays"; return 0; }
  [[ -x "${SCRIPTS}/apply-overlays.sh" ]] || die "missing scripts/apply-overlays.sh"
  log "Applying kernel / gamescope / MangoHud / Mesa / Decky / apps"
  "${SCRIPTS}/apply-overlays.sh"
}

build_box64() {
  if [[ -x "${R}/usr/local/bin/box64" ]] \
      && ! strings "${R}/usr/local/bin/box64" | grep -q 'GLIBC_2\.43'; then
    log "Box64 already in rootfs (Frame glibc) — skip rebuild"
    return 0
  fi
  if [[ "$SKIP_BOX64" -eq 1 ]]; then
    die "Box64 missing or needs GLIBC_2.43, and --skip-box64 is set"
  fi
  if [[ ! -d "${BOX64_SRC}/.git" && ! -f "${BOX64_SRC}/CMakeLists.txt" ]]; then
    log "Cloning ptitSeb/box64"
    git clone --recursive --depth 1 https://github.com/ptitSeb/box64 "${BOX64_SRC}"
  fi
  log "Building Box64 inside Frame rootfs (glibc 2.39, SD8G2)"
  "${SCRIPTS}/build-box64-in-rootfs.sh" "${R}"
}

install_box64_rootfs() {
  [[ -x "${BOX64_BUILD}/box64" ]] || die "box64 binary missing — build first"
  log "Installing Box64 into rootfs (no menu / no updater)"
  DESTDIR="${R}" cmake --install "${BOX64_BUILD}"
  rm -f "${R}/usr/local/share/applications/box64-configurator.desktop"
  rm -f "${R}/usr/local/bin/box64-configurator"
  rmdir "${R}/usr/local/share/applications" 2>/dev/null || true
  ln -sfn /usr/local/bin/box64 "${R}/usr/bin/box64"
  if [[ -f "${R}/etc/binfmt.d/box64.conf" ]]; then
    mkdir -p "${R}/usr/lib/binfmt.d"
    cp -a "${R}/etc/binfmt.d/box64.conf" "${R}/usr/lib/binfmt.d/box64.conf"
  fi
}

prepare_runtime() {
  log "Installing shared runtime before the TB520FU-specific override"
  install -D -m0755 "${OVL}/usr/lib/steamos/steamos-sm8550-expand-home" \
    "${R}/usr/lib/steamos/steamos-sm8550-expand-home"
  install -D -m0644 "${OVL}/usr/lib/systemd/system/steamos-sm8550-expand-home.service" \
    "${R}/usr/lib/systemd/system/steamos-sm8550-expand-home.service"
  mkdir -p "${R}/etc/systemd/system/multi-user.target.wants" \
    "${R}/etc/systemd/system/local-fs.target.wants" \
    "${R}/usr/lib/systemd/system/multi-user.target.wants" \
    "${R}/usr/lib/systemd/system/local-fs.target.wants"
  ln -sfn /usr/lib/systemd/system/steamos-sm8550-expand-home.service \
    "${R}/etc/systemd/system/multi-user.target.wants/steamos-sm8550-expand-home.service"
  ln -sfn /usr/lib/systemd/system/steamos-sm8550-expand-home.service \
    "${R}/etc/systemd/system/local-fs.target.wants/steamos-sm8550-expand-home.service"
  ln -sfn /usr/lib/systemd/system/steamos-sm8550-expand-home.service \
    "${R}/usr/lib/systemd/system/multi-user.target.wants/steamos-sm8550-expand-home.service"
  ln -sfn /usr/lib/systemd/system/steamos-sm8550-expand-home.service \
    "${R}/usr/lib/systemd/system/local-fs.target.wants/steamos-sm8550-expand-home.service"
  if [[ -x /usr/bin/growpart ]]; then
    install -D -m0755 /usr/bin/growpart "${R}/usr/bin/growpart"
  fi
  install -D -m0755 "${OVL}/usr/lib/steamos/sm8550-fixpad" \
    "${R}/usr/lib/steamos/sm8550-fixpad"
  install -D -m0644 "${OVL}/usr/lib/systemd/system/sm8550-fixpad.service" \
    "${R}/usr/lib/systemd/system/sm8550-fixpad.service"
  ln -sfn /usr/lib/systemd/system/sm8550-fixpad.service \
    "${R}/etc/systemd/system/multi-user.target.wants/sm8550-fixpad.service"
  install -D -m0644 "${OVL}/usr/lib/udev/rules.d/70-sm8550-gamepad.rules" \
    "${R}/usr/lib/udev/rules.d/70-sm8550-gamepad.rules"
  install -D -m0644 "${OVL}/usr/lib/udev/rules.d/70-sm8550-gamepad.rules" \
    "${R}/lib/udev/rules.d/70-sm8550-gamepad.rules"
  install -D -m0644 "${OVL}/etc/sdl2/qcom-gamecontrollerdb.txt" \
    "${R}/etc/sdl2/qcom-gamecontrollerdb.txt"
  install -D -m0644 "${OVL}/usr/lib/environment.d/60-sm8550-gamepad.conf" \
    "${R}/usr/lib/environment.d/60-sm8550-gamepad.conf"
  install -D -m0644 "${OVL}/etc/profile.d/sm8550-gamepad.sh" \
    "${R}/etc/profile.d/sm8550-gamepad.sh"
  install -D -m0755 "${OVL}/usr/lib/steamos/gamescope-session" \
    "${R}/usr/lib/steamos/gamescope-session"
  install -D -m0644 "${OVL}/etc/systemd/journald.conf.d/99-sm8550-persist.conf" \
    "${R}/etc/systemd/journald.conf.d/99-sm8550-persist.conf"
  mkdir -p "${R}/var/log/journal" \
    "${R}/etc/systemd/system/graphical.target.wants"
  rm -f "${R}/usr/lib/steamos/sm8550-hide-console" \
        "${R}/usr/lib/systemd/system/sm8550-hide-console.service" \
        "${R}/lib/systemd/system/sm8550-hide-console.service" \
        "${R}/etc/systemd/system/graphical.target.wants/sm8550-hide-console.service" \
        "${R}/etc/systemd/system/sysinit.target.wants/sm8550-hide-console.service" \
        "${R}/etc/systemd/system/multi-user.target.wants/sm8550-hide-console.service" \
        "${R}/usr/lib/systemd/system/graphical.target.wants/sm8550-hide-console.service" \
        "${R}/usr/lib/systemd/system/sysinit.target.wants/sm8550-hide-console.service" \
        "${R}/usr/lib/systemd/system/multi-user.target.wants/sm8550-hide-console.service" \
        "${R}/etc/systemd/system/multi-user.target.wants/sm8550-boot-debug.service" \
        "${R}/etc/systemd/system/graphical.target.wants/sm8550-boot-debug-late.service"
  "${SCRIPTS}/install-inputplumber-sm8550.sh" "${R}"

  # pkexec/sudo lose setuid when the rootfs is copied as a normal user.
  # Keep the boot oneshot even for --image-only.
  if [[ -x "${OVL}/usr/lib/steamos/sm8550-restore-privs" ]]; then
    install -D -m0755 "${OVL}/usr/lib/steamos/sm8550-restore-privs" \
      "${R}/usr/lib/steamos/sm8550-restore-privs"
    install -D -m0644 "${OVL}/usr/lib/systemd/system/sm8550-restore-privs.service" \
      "${R}/usr/lib/systemd/system/sm8550-restore-privs.service"
    mkdir -p "${R}/etc/systemd/system/multi-user.target.wants"
    ln -sfn /usr/lib/systemd/system/sm8550-restore-privs.service \
      "${R}/etc/systemd/system/multi-user.target.wants/sm8550-restore-privs.service"
    if [[ -d "${R}/var/lib/overlays/etc/upper" ]]; then
      mkdir -p "${R}/var/lib/overlays/etc/upper/systemd/system/multi-user.target.wants"
      ln -sfn /usr/lib/systemd/system/sm8550-restore-privs.service \
        "${R}/var/lib/overlays/etc/upper/systemd/system/multi-user.target.wants/sm8550-restore-privs.service" \
        || true
    fi
  fi
  if [[ -x "${OVL}/usr/bin/steamos-set-root-password" ]]; then
    install -D -m0755 "${OVL}/usr/bin/steamos-set-root-password" \
      "${R}/usr/bin/steamos-set-root-password"
  fi
}

restore_image_suid() {
  local dest="$1" p
  [[ -d "${dest}/usr/bin" ]] || return 0
  log "Restoring setuid root on pkexec/sudo in the image"
  for p in \
    usr/bin/pkexec usr/sbin/pkexec usr/bin/sudo usr/sbin/sudo \
    usr/lib/polkit-1/polkit-agent-helper-1 \
    usr/bin/su usr/bin/passwd usr/bin/newgrp usr/bin/chsh usr/bin/chfn \
    usr/bin/gpasswd usr/bin/unix_chkpwd usr/bin/mount usr/bin/umount
  do
    [[ -e "${dest}/${p}" ]] || continue
    sudo_run chown root:root "${dest}/${p}"
    sudo_run chmod 4755 "${dest}/${p}"
  done
  if [[ -e "${dest}/usr/lib/dbus-1.0/dbus-daemon-launch-helper" ]]; then
    # The dbus package ships it root:dbus 4750 (the bus daemon runs it as
    # dbus). Take the group number from the image, not the build host.
    local dbus_gid
    dbus_gid="$(awk -F: '$1 == "dbus" {print $3}' "${dest}/etc/group" 2>/dev/null)"
    sudo_run chown "root:${dbus_gid:-root}" "${dest}/usr/lib/dbus-1.0/dbus-daemon-launch-helper"
    sudo_run chmod 4750 "${dest}/usr/lib/dbus-1.0/dbus-daemon-launch-helper"
  fi
}

wait_loop_parts() {
  local dev="$1" i
  for i in $(seq 1 50); do
    [[ -b "${dev}p1" && -b "${dev}p2" && -b "${dev}p3" ]] && return 0
    sleep 0.1
  done
  die "loop partitions did not appear on ${dev}"
}

cleanup_image() {
  sync || true
  sudo_run umount "${MNT}/boot" 2>/dev/null || true
  sudo_run umount "${MNT}/home" 2>/dev/null || true
  sudo_run umount "${MNT}/root" 2>/dev/null || true
  if [[ -n "${LOOPDEV:-}" ]]; then
    sudo_run losetup -d "${LOOPDEV}" 2>/dev/null || true
    LOOPDEV=""
  fi
}

detach_img_loops() {
  local dev
  sudo_run umount "${MNT}/boot" 2>/dev/null || true
  sudo_run umount "${MNT}/home" 2>/dev/null || true
  sudo_run umount "${MNT}/root" 2>/dev/null || true
  while read -r dev; do
    [[ -n "${dev}" ]] || continue
    sudo_run losetup -d "${dev}" 2>/dev/null || true
  done < <(losetup -j "${IMG}" -O NAME -n 2>/dev/null || true)
}

build_image() {
  local total_mib root_uuid home_uuid disk_id
  local boot_dev root_dev home_dev
  command -v sfdisk >/dev/null || die "sfdisk missing"
  command -v mkfs.vfat >/dev/null || die "mkfs.vfat missing"
  command -v mkfs.ext4 >/dev/null || die "mkfs.ext4 missing"
  command -v uuidgen >/dev/null || die "uuidgen missing"
  [[ -x "${R}/usr/bin/bash" ]] || die "rootfs not ready"
  [[ -f "${KOUT}/boot/Image" ]] || die "missing ${KOUT}/boot/Image"
  if [[ -n "${TB520FU_UEFI_BOOT_IMG:-}" ]]; then
    [[ -s "$TB520FU_UEFI_BOOT_IMG" && "${TB520FU_UEFI_SHA256:-}" =~ ^[a-f0-9]{64}$ ]] || die "explicit TB520FU UEFI image/SHA256 required"
  else
    [[ -s "$ROOT/external-and-mods/tb520fu/uefi/release.env" ]] || die "TB520FU UEFI release lock missing"
  fi

  if [[ "${AUTO_ROOT}" -eq 1 ]]; then
    local used_mib
    used_mib="$(du -sm \
      --exclude=home --exclude=boot --exclude=proc --exclude=sys \
      --exclude=dev --exclude=tmp --exclude=run --exclude='opt/tb520fu-build' \
      --exclude='opt/tb520fu-runtime-stage' --exclude='root/.cargo' --exclude='var/cache/pacman/pkg' --exclude='.image-mnt' \
      "${R}" | awk '{print $1}')"
    # ~500 MiB free after 1% reserved blocks + a little slack for first boot.
    # 1.5 GiB free at pack: 500 MiB filled on first boot last time (root 100%).
    ROOT_MIB=$((used_mib + 1536 + used_mib / 100 + 128))
    log "root auto-size ${ROOT_MIB} MiB (rootfs ${used_mib} MiB, ~1.5 GiB free)"
  fi
  if [[ "${AUTO_HOME}" -eq 1 ]]; then
    local home_mib
    home_mib="$(du -sm "${R}/home" 2>/dev/null | awk '{print $1}')"
    home_mib="${home_mib:-1}"
    HOME_MIB=$((home_mib + 256 + home_mib / 100 + 32))
    log "home auto-size ${HOME_MIB} MiB (payload ${home_mib} MiB; grows on first boot)"
  fi

  total_mib=$((BOOT_MIB + ROOT_MIB + HOME_MIB + 2))
  # MBR disk id is recorded for diagnostics; the initramfs selects root by UUID.
  disk_id="$(od -An -N4 -tx4 /dev/urandom | tr -d ' ')"
  root_uuid="$(uuidgen)"
  home_uuid="$(uuidgen)"

  [[ ! -b "$IMG" && ! -c "$IMG" && ! -L "$IMG" ]] || die "image output must be a regular file path"
  log "Creating ${IMG} (${total_mib} MiB sparse)"
  log "  p1 BOOT ${BOOT_MIB}M vfat"
  log "  p2 root ${ROOT_MIB}M ext4 UUID=${root_uuid}"
  log "  p3 home ${HOME_MIB}M ext4 UUID=${home_uuid} (grows on first boot)"

  detach_img_loops
  rm -f "${IMG}"
  truncate -s "${total_mib}M" "${IMG}"

  # util-linux 2.41+ sfdisk dump format only accepts unit: sectors (not MiB).
  # 1 MiB = 2048 × 512-byte sectors. Layout is unchanged: 1MiB gap, BOOT, root, home.
  sfdisk "${IMG}" <<EOF
label: dos
label-id: 0x${disk_id}
unit: sectors

start=2048, size=$((BOOT_MIB * 2048)), type=c, bootable
size=$((ROOT_MIB * 2048)), type=83
type=83
EOF

  LOOPDEV="$(sudo_run losetup -f --show -P "${IMG}")"
  [[ -n "${LOOPDEV}" ]] || die "losetup failed"
  log "loop ${LOOPDEV}"
  wait_loop_parts "${LOOPDEV}"
  boot_dev="${LOOPDEV}p1"
  root_dev="${LOOPDEV}p2"
  home_dev="${LOOPDEV}p3"

  trap cleanup_image EXIT

  sudo_run mkfs.vfat -F 32 -n BOOT "${boot_dev}"
  sudo_run mkfs.ext4 -F -L root -U "${root_uuid}" -m 1 "${root_dev}"
  sudo_run mkfs.ext4 -F -L home -U "${home_uuid}" -m 1 "${home_dev}"

  mkdir -p "${MNT}/boot" "${MNT}/root" "${MNT}/home"
  sudo_run mount "${root_dev}" "${MNT}/root"
  sudo_run mount "${home_dev}" "${MNT}/home"
  sudo_run mount "${boot_dev}" "${MNT}/boot"

  log "Copying root filesystem"
  sudo_run rsync -aHAX --numeric-ids --info=progress2 \
    --exclude='/home/**' \
    --exclude='/boot/**' \
    --exclude='/dev/**' \
    --exclude='/proc/**' \
    --exclude='/sys/**' \
    --exclude='/tmp/**' \
    --exclude='/run/**' \
    --exclude='/opt/tb520fu-build/**' \
    --exclude='/opt/tb520fu-runtime-stage/**' \
    --exclude='/root/.cargo/**' \
    --exclude='/var/cache/pacman/pkg/**' \
    "${R}/" "${MNT}/root/"

  sudo_run mkdir -p "${MNT}/root/boot" "${MNT}/root/home" \
    "${MNT}/root/dev" "${MNT}/root/proc" "${MNT}/root/sys" \
    "${MNT}/root/tmp" "${MNT}/root/run"

  # rsync as root can copy steam:steam binaries; restore setuid now so
  # Decky / MESA / UFS ask for the user password on first boot.
  restore_image_suid "${MNT}/root"
  # Each new installation must generate its own D-Bus/network identity.
  sudo_run truncate -s 0 "${MNT}/root/etc/machine-id"
  if [[ -f "${MNT}/root/var/lib/overlays/etc/upper/machine-id" ]]; then
    sudo_run truncate -s 0 "${MNT}/root/var/lib/overlays/etc/upper/machine-id"
  fi


  log "Copying /home/steamos"
  if [[ -d "${R}/home/steamos" ]]; then
    sudo_run mkdir -p "${MNT}/home/steamos"
    sudo_run rsync -aHAX --numeric-ids "${R}/home/steamos/" "${MNT}/home/steamos/"
    sudo_run chown -hR 1000:1000 "${MNT}/home/steamos"
  fi

  log "Writing fstab and TB520FU EFI boot files (root UUID ${root_uuid})"
  # SteamOS mounts /etc from the overlay. Write both layers so first boot
  # actually uses this 3-partition layout (and home can grow).
  sudo_run tee "${MNT}/root/etc/fstab" >/dev/null <<EOF
# SteamOS ARM (${SOC}) — PC/handheld layout (not Steam Deck A/B)
UUID=${root_uuid}  /      ext4  defaults,noatime                         0 1
LABEL=BOOT         /boot  vfat  defaults,umask=0077,nofail               0 2
UUID=${home_uuid}  /home  ext4  defaults,noatime,commit=30,x-systemd.growfs 0 2
EOF
  sudo_run mkdir -p "${MNT}/root/var/lib/overlays/etc/upper"
  sudo_run cp -a "${MNT}/root/etc/fstab" "${MNT}/root/var/lib/overlays/etc/upper/fstab"

  local tb_cmdline
  tb_cmdline="root=UUID=${root_uuid} rootfstype=ext4 rw rootwait firmware_class.path=/usr/lib/firmware/steamos-arm/tb520fu fw_devlink.sync_state=timeout drm_client_lib.active=none console=tty0 loglevel=4"
  sudo_run env STEAMOS_WORK="$WORKDIR" \
    TB520FU_UEFI_BOOT_IMG="${TB520FU_UEFI_BOOT_IMG:-}" TB520FU_UEFI_SHA256="${TB520FU_UEFI_SHA256:-}" \
    bash "${SCRIPTS}/stage-tb520fu-boot.sh" "${MNT}/boot" "$KOUT" "${TB520FU_PANEL:-both}" "$tb_cmdline"

  sudo_run mkdir -p "${MNT}/root/opt/steamos-sm8650"
  sudo_run tee "${MNT}/root/opt/steamos-sm8650/IMAGE.txt" >/dev/null <<EOF
image=$(basename "${IMG}")
soc=${SOC}
kernel=$(basename "$(readlink -f "${KOUT}")")
built=$(date -Iseconds)
root_uuid=${root_uuid}
root_partuuid=${disk_id}-02
home_uuid=${home_uuid}
boot_label=BOOT
layout=vfat-boot + ext4-root + ext4-home
expand=steamos-sm8550-expand-home.service
EOF

  sudo_run tee "${MNT}/boot/README.txt" >/dev/null <<EOF
TB520FU development image. EFI/BOOT/grub.cfg selects the panel-specific DTB.
Root filesystem UUID=${root_uuid}
tablet/tb520fu-uefi-boot.img contains the experimental TB520FU UEFI.
No ROCKNIX ABL, Y700 boot image or internal-storage installer is included.
Linux boot and hardware operation have not been verified.
EOF

  sync
  cleanup_image
  trap - EXIT

  log "Image ready: ${IMG}"
  log "$(ls -lh "${IMG}")"
  log "Development image prepared; verify the TB520FU boot chain before use."
}

if [[ "$IMAGE_ONLY" -eq 0 ]]; then
  ensure_official_rootfs
  apply_mods
  build_box64
fi
# An imported common rootfs must use only this port's modules. This also
# refreshes modules when --image-only is used after a new kernel build.
[[ -f "$R/.tb520fu-rootfs" && "$R" != / ]] || die "dedicated rootfs marker missing"
sudo_run mkdir -p "$R/usr/lib/modules" "$R/boot"
sudo_run find "$R/usr/lib/modules" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
sudo_run cp -a "$KOUT/modules/$(basename "$KOUT")" "$R/usr/lib/modules/"
sudo_run cp "$KOUT/boot/KERNEL" "$KOUT/boot/KERNEL.md5" "$R/boot/"
# Always refresh runtime bits before packing
[[ -x "${R}/usr/local/bin/box64" ]] || install_box64_rootfs
# Decky's plugin_loader.service execs /usr/bin/box64. A rootfs that already
# had box64 skips install_box64_rootfs, so make the link here too.
ln -sfn /usr/local/bin/box64 "${R}/usr/bin/box64"
prepare_runtime
if [[ "$PREPARE_ROOTFS_ONLY" == 1 ]]; then
  log "Base TB520FU rootfs prepared: $R"
  log "Next: scripts/build-tb520fu-runtime.sh '$R', then $0 --image-only"
  exit 0
fi
runtime="${TB520FU_RUNTIME_STAGE:-$R/opt/tb520fu-runtime-stage}"
if [[ ! -f "$runtime/TB520FU-RUNTIME.json" ]]; then
  sudo_run env BUILD_JOBS="${BUILD_JOBS:-2}" TB520FU_SOURCE_DIR="${TB520FU_SOURCE_DIR:-}" \
    bash "$SCRIPTS/build-tb520fu-runtime.sh" "$R"
fi
firmware="${TB520FU_FIRMWARE:-$ROOT/external-and-mods/tb520fu/local/firmware-lenovo-tb520fu.tar.gz}"
python3 "$SCRIPTS/install-tb520fu.py" --rootfs "$R" --runtime-stage "$runtime" --firmware "$firmware"
build_image
