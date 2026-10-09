# TB520FU integration sources

`source.env` pins the TB520FU kernel fork and the userspace components.
`firmware-manifest.json` is copied from that exact source commit.
Device runtime overlay files are adapted from that port; they are installed only
by the opt-in TB520FU recipe. See [the guide](../../docs/tb520fu.md).

The source port builds on Armada, enij90's TB321FU port, GUF296's kernel/sensor/GRUB
work and ROCKNIX. Each component retains its original license. In particular,
libssc, hexagonrpc, the sensor proxy and IMU bridge retain their GPL-3.0-or-later
licenses; the kernel patches and InputPlumber retain their upstream licenses.
The stock firmware archive is a local input, ignored by Git and not redistributed.
The shared GRUB programs are generic ARM64 binaries; the Y700 UEFI boot image and
its device-specific memory-map edits are not used for TB520FU.

The device-specific UEFI source is in [uefi/](uefi/README.md), based on pinned
Mu-Silicium Lanai support and locally extracted TB520FU stock modules. Only
source preparation was executed. No UEFI boot.img has been compiled or booted.
