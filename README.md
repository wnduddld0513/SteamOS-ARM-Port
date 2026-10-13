# SteamOS ARM for TB520FU

> [!WARNING]
> Boot logs show SteamOS userspace starting, but display output is still broken. GRUB and Linux kernel loading messages appear, then the screen turns off and no picture is displayed. A working desktop or Game Mode has not been confirmed. This port is experimental.

This fork ports the TB321FU Linux and SteamOS integration to the Lenovo Yoga Tab Plus (TB520FU, SM8650). It adapts the boot process, kernel and userspace configuration to TB520FU using the tablet's own stock device trees, firmware and hardware settings.

Development takes place on the `tb520fu` branch. The [TB520FU installation and build guide](docs/tb520fu.md) describes the current internal UFS layout and known limitations.

## Current status

| Component | Status |
| --- | --- |
| Dedicated TB520FU UEFI | Starts; boot menu and hardware buttons work |
| Internal UFS and GRUB | Detected; panel selection works |
| Linux 7.2.6 | Starts and prints boot messages |
| SteamOS userspace | Startup confirmed in captured logs |
| Desktop / Game Mode display | No usable output after boot messages |
| Remaining hardware | Full operation under SteamOS remains unverified |

The kernel and OS have been built locally. Successful compilation and userspace startup do not establish a working graphical session.

## Installation

The current path boots from internal storage and does not require a USB boot drive.

| Image | Partition | Purpose |
| --- | --- | --- |
| `boot.img` | `boot_a` | TB520FU UEFI |
| `super.img` | `super` | FAT32 boot filesystem with GRUB, kernel and DTBs |
| `userdata.simg` | `userdata` | ext4 SteamOS system and home directory |

Installation replaces Android system and user data and overwrites the selected boot image. Use a matching image bundle, back up first, and follow the [internal installation instructions](docs/tb520fu.md#install-on-internal-storage). The guide also covers compatible `super.img`-only updates.

## Display configuration

Tianma and BOE NT36532 panels have separate device trees and stock initialization sequences. Both are configured for 2944 x 1840 in landscape at 120 Hz, with dual DSI and DSC 1.1 SCR1. Select the fitted panel in GRUB; Tianma is the default. Automatic detection and additional refresh rates are not implemented.

Native display output, touch and pen alignment, brightness behavior and suspend/resume still need validation. See the [hardware inventory](https://github.com/wnduddld0513/linux-tb520fu/blob/main/tb520fu/HARDWARE.md) for implementation scope and remaining work.

## Source and building

The [TB520FU kernel repository](https://github.com/wnduddld0513/linux-tb520fu) supplies the patches, device trees and kernel configuration. This OS branch pins kernel commit [`fcf8cd2`](https://github.com/wnduddld0513/linux-tb520fu/commit/fcf8cd2513b429fa54ac418c33ced27d1ed0815e).

```bash
git clone --branch tb520fu https://github.com/wnduddld0513/SteamOS-ARM-Port.git
cd SteamOS-ARM-Port
bash tools/setup-fork.sh
```

Follow the [build instructions](docs/tb520fu.md#build-from-source) for the kernel, dedicated UEFI, ARM64 runtime and internal-install images. Stock firmware is supplied locally and verified against the [firmware manifest](external-and-mods/tb520fu/firmware-manifest.json). Firmware binaries and local build outputs are not committed to Git.

For boot diagnostics, see [logs and verification](docs/tb520fu.md#logs-and-verification). Include captured kernel and journal logs when reporting the display failure through this fork's [issues](https://github.com/wnduddld0513/SteamOS-ARM-Port/issues).

## Credits and license

Based on [SteamOS ARM Port](https://github.com/hashtagbasit/SteamOS-ARM-Port) and the [TB321FU Linux port](https://github.com/enij90/armada-tb321fu), with contributions from GUF296, Project Silicium and the projects listed in [CREDITS.md](CREDITS.md).

See [LICENSE](LICENSE) for project and component licenses. This is an unofficial community port and is not affiliated with or endorsed by Valve or Lenovo.
