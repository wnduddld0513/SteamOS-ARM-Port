<p align="center">
  <a href="https://steamos-arm-port.github.io/">
    <img src=".github/assets/logo.svg" alt="SteamOS ARM Port" width="112">
  </a>
</p>

<h1 align="center">SteamOS ARM Port for TB520FU</h1>

<p align="center">Unofficial SteamOS for Snapdragon handhelds</p>

<p align="center">
  Valve's SteamOS for ARM, the one made for the Steam Frame, set up for handhelds:
  Game Mode, the KDE desktop, PC games through FEX and Proton, and Android apps.
</p>

<p align="center">
  <a href="https://github.com/hashtagbasit/SteamOS-ARM-Port/releases"><img alt="Latest release" src="https://img.shields.io/github/v/release/hashtagbasit/SteamOS-ARM-Port?include_prereleases&style=flat&color=7c5cf0&label=release"></a>
  <a href="https://steamos-arm-port.github.io/"><img alt="Documentation" src="https://img.shields.io/badge/docs-steamos--arm--port.github.io-18181a?style=flat"></a>
  <a href="LICENSE"><img alt="GPL-2.0 license" src="https://img.shields.io/badge/license-GPL--2.0-18181a?style=flat"></a>
  <a href="https://discord.gg/EP53nZYvg"><img alt="Discord" src="https://img.shields.io/badge/chat-Discord-5865F2?style=flat&amp;logo=discord&amp;logoColor=white"></a>
</p>

<p align="center">
  <a href="https://steamos-arm-port.github.io/getting-started/install/">Install it</a>
  ·
  <a href="https://steamos-arm-port.github.io/devices/">Supported devices</a>
  ·
  <a href="https://steamos-arm-port.github.io/downloads/">Downloads</a>
  ·
  <a href="https://steamos-arm-port.github.io/help/known-issues/">Known issues</a>
</p>

> [!WARNING]
> This is a community project, not affiliated with or endorsed by Valve.
> The upstream installation path uses the ROCKNIX ABL bootloader. Getting that
> wrong can leave your device unable to boot or lose your data. Back up first
> and follow the [install guide](https://steamos-arm-port.github.io/getting-started/install/)
> step by step.


This repository contains the TB520FU port for the Lenovo Yoga Tab Plus / YOGA Pad Pro AI元启 (Snapdragon 8 Gen 3). Development takes place on `main`. The TB520FU kernel, Tianma and BOE device trees, UEFI boot image, ARM64 runtime and USB image have been built locally. Boot and hardware operation on the tablet remain untested.

Start with the [TB520FU guide](docs/tb520fu.md). TB520FU uses a separate experimental UEFI and USB boot path; the upstream ABL flashing and internal installation instructions below do not apply to this device. Other device recipes are retained from the upstream project.

## About

Valve's ARM build of SteamOS is made for a VR headset, so out of the box a lot
of it gets in the way on a handheld: services that keep crashing, the UI stuck
on the slow cores, the GPU not clocking up, standby that drains the battery. I
turned off what a handheld doesn't need and fixed the rest, the long version
is in [HOW-IT-WORKS.md](docs/HOW-IT-WORKS.md).

What you get:

- Game Mode and Desktop Mode, with the controller showing up as a Steam Deck pad
- x86 PC games through FEX and ARM64 Proton, plus Epic, GOG and Amazon through Heroic
- Loadout, which installs emulators and apps picked for your SoC
- Sleep that lasts and quiet fan curves
- Updates through Steam, no reflashing
- Lossless Scaling frame gen, Decky and the performance overlay
- Android apps with the Play Store
- A dashboard on the bottom screen of the AYN Thor and AYANEO Pocket DS

## Devices

### Handhelds

| SoC | Devices | Status |
|---|---|---|
| Snapdragon 8 Elite | AYN Odin 3, KONKR Pocket FIT Elite | Stable |
| Snapdragon 8 Gen 3 | KONKR Pocket FIT, AYANEO Pocket S2 / S2 Pro | Stable |
| Snapdragon 8 Gen 2 | AYN Odin 2 / Mini / Portal / Thor, AYANEO Pocket ACE / DMG / DS / EVO / S 1K / S 2K, Retroid Pocket 6 / Nova | Stable |

There's one image per SoC, you pick your device in the ABL menu and it sets
itself up. I only own a Pocket FIT, so if you have one of the others please
[let me know how it runs](https://github.com/hashtagbasit/SteamOS-ARM-Port/issues).

### Phones & tablets

| Device | SoC | Status |
|---|---|---|
| Lenovo Legion Y700 Gen 3 (TB321FU) | Snapdragon 8 Gen 3 | Testing |
| Lenovo Legion Y700 Gen 4 (TB322FC) | Snapdragon 8 Elite | Testing |
| Lenovo Yoga Tab Plus / YOGA Pad Pro AI元启 (TB520FU) | Snapdragon 8 Gen 3 | Experimental TB520FU build — [TB520FU guide](docs/tb520fu.md) |
| REDMAGIC 6 (NX669J) | Snapdragon 888 | Build it yourself ([guide](docs/redmagic6.md)) |

The Lenovo tablets boot from a USB drive and install to internal storage,
nobody has run them on a real tablet yet. If you have one and want to help,
ask on [Discord](https://discord.gg/EP53nZYvg) and see the
[Lenovo page](https://steamos-arm-port.github.io/devices/lenovo/).

### TB520FU development

The `main` branch adds an opt-in, separate TB520FU image recipe using
[our TB520FU kernel port](https://github.com/wnduddld0513/linux-tb520fu/tree/main).
It includes Tianma and BOE panel configurations (2944×1840, currently 120 Hz).
Existing device builders and overlays are unchanged. The Linux 7.2.6 kernel,
modules, both panel DTBs and dedicated [TB520FU UEFI boot image](external-and-mods/tb520fu/uefi/README.md)
have been compiled and inspected. The ARM64 sensor/input/audio runtime and USB
image have also been built and checked. The completed image and UEFI boot image are local build artifacts and have not been published to GitHub Releases.
Linux boot and hardware operation on the tablet remain untested.
See [docs/tb520fu.md](docs/tb520fu.md) for the dedicated paths and limitations.

## Documentation

Everything lives on the [website](https://steamos-arm-port.github.io/).

| I want to… | Guide |
|---|---|
| Install it | [Flash to a microSD card](https://steamos-arm-port.github.io/getting-started/install/) |
| Check my device | [Supported devices](https://steamos-arm-port.github.io/devices/) |
| Move it to internal storage | [Internal storage](https://steamos-arm-port.github.io/getting-started/internal-storage/) |
| Update | [Updates](https://steamos-arm-port.github.io/using/updates/) |
| Get help | [FAQ](https://steamos-arm-port.github.io/help/faq/) · [Troubleshooting](https://steamos-arm-port.github.io/help/troubleshooting/) |
| Report a bug | [GitHub issues](https://github.com/hashtagbasit/SteamOS-ARM-Port/issues) |

## Building

The images are built from this repo on an ARM64 Linux machine, see
[docs/building.md](docs/building.md). Issues and pull requests are welcome,
and for help with installing come say hi on [Discord](https://discord.gg/EP53nZYvg).

## Supporting the project

<p align="left">
  <a href="https://ko-fi.com/aimalb"><img src="https://img.shields.io/badge/Ko--fi-Buy%20me%20a%20coffee-ff5e5b?style=for-the-badge&logo=kofi&logoColor=white" alt="Ko-fi"></a>
  <a href="https://paypal.me/Basit2000"><img src="https://img.shields.io/badge/PayPal-Basit2000-00457c?style=for-the-badge&logo=paypal&logoColor=white" alt="PayPal"></a>
</p>

Any amount raised will be used to buy devices to support and boost development, a star helps too!

Have a device you'd like to see supported? Sending one over for long term
development is the fastest way to get it there, message me on
[Discord](https://discord.gg/EP53nZYvg).

## Credits

The kernels and device support come from [ROCKNIX](https://github.com/ROCKNIX/distribution).
The full list of projects and people is in [CREDITS.md](CREDITS.md).

## License

My scripts and overlays are GPL-2.0, everything in `external-and-mods/` keeps
its own license. See [LICENSE](LICENSE).

Steam and SteamOS are trademarks of Valve Corporation, used here only to say
what this is based on. Please don't ask Valve for help with it.
