> [!WARNING]
> Boot logs confirm that SteamOS userspace starts, but display output is still broken. GRUB and Linux kernel loading messages appear, then the screen turns off and no picture is displayed. A working SteamOS desktop or Game Mode has not been confirmed. This is an experimental port, not a usable release.

# SteamOS ARM for Lenovo TB520FU

This branch targets the Lenovo Yoga Tab Plus / YOGA Pad Pro AI Yuanqi (TB520FU, lapis, Snapdragon 8 Gen 3 / SM8650). Development takes place on [`tb520fu`](https://github.com/wnduddld0513/SteamOS-ARM-Port-TB520FU/tree/tb520fu).

The current installation uses internal UFS storage. A USB boot drive is not required. The earlier external USB image and RAM partition handoff instructions are not the current installation path.

## Current status

| Stage | Observed status |
| --- | --- |
| TB520FU UEFI | Starts; boot menu and hardware buttons work |
| Internal UFS and GRUB | Detected; GRUB and panel selection appear |
| Linux kernel | Starts and prints boot messages |
| SteamOS userspace | Startup is visible in captured logs |
| Desktop / Game Mode display | No usable output after the boot messages; unresolved |
| Other hardware under SteamOS | Full operation remains unverified |

A blank screen alone does not establish whether Linux has stopped. Captured logs have shown userspace continuing after display output was lost; behavior varies between test builds.

## Images and boot layout

Use TB520FU images from a matching internal-install bundle.

| File | Flash target | Contents |
| --- | --- | --- |
| `boot.img` | `boot_a` | Dedicated TB520FU UEFI |
| `super.img` | `super` | FAT32 boot filesystem with ARM64 GRUB, Linux Image and panel DTBs |
| `userdata.simg` | `userdata` | Android sparse image containing the ext4 SteamOS root filesystem and home directory |
| `SHA256SUMS` | Do not flash | Image checksums |
| `internal-image.json` | Do not flash | Build provenance, root UUID and image hashes |

The boot sequence is:

```text
boot_a: TB520FU UEFI
  -> super: FAT32 / EFI / GRUB
  -> Linux EFI stub + selected panel DTB
  -> userdata: ext4 root filesystem
  -> SteamOS userspace
```

The root UUID in GRUB must match the userdata filesystem. Kernel and installed modules must also match. Use the bundle's checksums rather than hashes from older releases. Files named `image.json` describe subsequent test updates and may list only `super.img`.

## Install on internal storage

This procedure replaces Android's `super` and `userdata` contents and overwrites `boot_a`. Back up Android data and recovery images first. An existing recovery on the affected boot slot may no longer be available. The bootloader must already be unlocked, and the matching stock firmware must be available for restoration.

Install Android platform-tools on the computer. Put the matching `boot.img`, `super.img` and `userdata.simg` in one directory, then connect the tablet in bootloader fastboot mode.

From Windows Command Prompt, open that directory and run:

```bat
fastboot devices
fastboot set_active a
fastboot flash boot_a boot.img
fastboot flash super super.img
fastboot -S 700M flash userdata userdata.simg
fastboot reboot
```

Run the next flashing command only if the previous one succeeds. These commands do not flash ABL or replace the GPT. Do not use Y700/Y703 boot images, flash `boot/KERNEL`, or add `fastboot format userdata`: this layout needs the ext4 filesystem written by `userdata.simg`.

For an existing compatible internal installation, a test update supplied as `super.img` only is applied with:

```bat
fastboot set_active a
fastboot flash super super.img
fastboot reboot
```

Use this shorter procedure only when the update explicitly retains the installed UEFI, root UUID and module compatibility. Reflashing `userdata.simg` replaces the installed system and home directory.

### Boot menu

Use the volume buttons to move and the power button to confirm, as Enter. Select the entry for the fitted panel; Tianma is the default and BOE is separate. Automatic panel detection is not implemented.

The firmware display diagnostics entry keeps the inherited firmware framebuffer and disables native display ownership. It is for collecting logs, not a normal graphical session. The old RAM partition handoff fallback has faulted before Linux and should not be used as an installation or recovery method.

The display failure described at the top still applies after a successful flash. Reaching GRUB, kernel messages or systemd startup does not mean that the graphical session is working.

## Display and hardware configuration

The kernel is pinned to [linux-tb520fu at `fcf8cd2`](https://github.com/wnduddld0513/linux-tb520fu/commit/fcf8cd2513b429fa54ac418c33ced27d1ed0815e), using Linux 7.2.6 and the `7.2.6-tb520fu-steamos` release name.

| Panel | Native DTB | Touch firmware |
| --- | --- | --- |
| Tianma NT36532 | `sm8650-lenovo-tb520fu.dtb` | `novatek_ts_tianma_fw.bin` |
| BOE NT36532 | `sm8650-lenovo-tb520fu-boe.dtb` | `novatek_ts_boe_fw.bin` |

Both definitions use 2944 x 1840 in landscape at 120 Hz, dual four-lane DSI and DSC 1.1 SCR1. Additional stock refresh rates, HDR/HBM, pen alignment and suspend/resume need implementation or validation.

The internal image builder creates separate `-internal-display.dtb` variants with the DisplayPort controller disabled so that an unavailable DP bridge cannot defer the internal display component. The original DTBs are retained. Normal internal entries use `drm_client_lib.active=none`; the firmware diagnostic entry uses `fbdev`. These settings do not establish that the display fault is fixed.

See the [kernel hardware inventory](https://github.com/wnduddld0513/linux-tb520fu/blob/main/tb520fu/HARDWARE.md) for audio, Wi-Fi, Bluetooth, USB-C, charging, sensors, vibration, keyboard, NFC and camera scope. Camera capture and fingerprint authentication remain incomplete. Source support is not a claim that every device works under SteamOS.

## Build from source

Build on a Linux filesystem. On an x86 host, use the ARM64 cross compiler for the kernel and ARM64 QEMU/binfmt support for userspace chroots. The kernel initramfs requires a static ARM64 BusyBox with `findfs`. Follow the [build environment guide](building.md) and the pinned Mu project's toolchain requirements for UEFI.

```bash
git clone --branch tb520fu https://github.com/wnduddld0513/SteamOS-ARM-Port-TB520FU.git
cd SteamOS-ARM-Port-TB520FU
bash tools/setup-fork.sh

export STEAMOS_WORK=/work/tb520fu
export TB520FU_BUSYBOX=/path/to/static-arm64-busybox
export TB520FU_STOCK_DIR=/path/to/TB520FU-stock/image
```

Prepare the stock firmware archive at `external-and-mods/tb520fu/local/firmware-lenovo-tb520fu.tar.gz`, or set `TB520FU_FIRMWARE` to its location. The [firmware manifest](../external-and-mods/tb520fu/firmware-manifest.json) verifies 274 files and the archive SHA256. Proprietary firmware is not committed to Git.

Build the kernel, dedicated UEFI and TB520FU userspace image:

```bash
bash scripts/build-tb520fu-kernel.sh
bash scripts/build-tb520fu-uefi.sh --build "$TB520FU_STOCK_DIR"
sudo -E bash make-steamos-tb520fu.sh --base-release
```

The last command produces `$STEAMOS_WORK/steamos-tb520fu.img`. For the internal layout, this is a staging image consumed by the packer; it does not need to be written to a USB drive. Kernel, runtime and staging image must use the same pinned source. Rebuild stale stages after changing the pin.

Create the internal-install bundle in a new output directory:

```bash
UEFI_IMAGE="$STEAMOS_WORK/uefi/output/tb520fu-uefi-boot.img"
UEFI_SHA=$(sha256sum "$UEFI_IMAGE" | cut -d ' ' -f 1)

sudo python3 scripts/build-tb520fu-internal.py \
  --source-image "$STEAMOS_WORK/steamos-tb520fu.img" \
  --kernel-out "$STEAMOS_WORK/kernel/output/current" \
  --uefi-image "$UEFI_IMAGE" \
  --uefi-sha256 "$UEFI_SHA" \
  --output "$STEAMOS_WORK/internal-install" \
  --userdata-gib 20
```

The packer produces `boot.img`, `super.img`, `userdata.simg`, checksums and provenance. It validates the FAT/ext4 filesystems and compares the expanded sparse image against the raw userdata filesystem. It operates on local image files and private loop devices; it does not flash the tablet. Runtime filesystem growth does not repartition the Android GPT.

## Logs and verification

Current internal entries enable `tb520fu.diagnostics=1`. Once systemd starts, the logger captures kernel messages, journal output, deferred probes, DRM connectors and backlight state under `/tb520fu-boot-logs/<boot-id>/`. If `/boot` is mounted, snapshots are also copied to `/boot/tb520fu-logs/` on `super`. Pstore records are copied when available. A crash before the logger starts or before `/boot` mounts can leave no saved logs.

Read dumps without modifying them. Useful files are `dmesg.txt`, `journal.txt`, `state.txt`, `cmdline.txt` and any pstore records. The [diagnostic service](../external-and-mods/tb520fu/initramfs/tb520fu-boot-diagnostics.sh) defines the current capture paths.

Source checks can be run without flashing or building an image:

```bash
python3 tools/check-tb520fu.py
python3 scripts/install-tb520fu.py --check-firmware \
  --firmware external-and-mods/tb520fu/local/firmware-lenovo-tb520fu.tar.gz
```

TB520FU uses its own build entry points, overlay, firmware namespace and UEFI configuration. Other device recipes retain upstream behavior. Generic SoC OTA and repartition services are disabled in the TB520FU image; Steam client updates are separate.

`scx.service` is masked. The common SM8650 kernel is built without sched_ext, so the service's `/sys/kernel/sched_ext` condition never lets it start there. Kernel `f0daedc` enabled sched_ext; from `e4bbdb1` on, the TB520FU kernel disables it as well. In every captured boot of kernel `f0daedc`, logging stopped 2–5 seconds after `sched_ext: BPF scheduler "lavd_…" enabled`. That happened before Gamescope committed its first frame. Deckard's `set-bluetooth-mac-address.service` is also masked because it targets an EEPROM this tablet lacks. QCA Bluetooth firmware is installed under the `qca/` prefix that btqca requests.
