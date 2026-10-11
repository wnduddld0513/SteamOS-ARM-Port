# TB520FU UEFI port (experimental)

Dedicated Lenovo TB520FU / lapis / SM8650 support for pinned
[Mu-Silicium](https://github.com/Project-Silicium/Mu-Silicium/tree/8d73b66ab554f9ab6134b58839bb1e46ebd47688).
Preparation and source patches apply only to this device's private build
checkout. Existing device builders are unchanged.

The tablet has reached the UEFI boot manager. USB enumeration, button operation
and Linux entry remain unverified. v21 replaces successful no-op SPMI transfers
with real transfers and an ownership guard, and selects USB host mode only for
the tablet's single controller. It was compiled from a new Build directory and
passed host checks; it has not been booted on the tablet.

See the [Y703 comparison](../../../docs/tb520fu-y703-baseline.md),
[machine-readable comparison](../../../docs/tb520fu-y703-comparison.json) and
[debug history](../../../docs/tb520fu-uefi-debug.md). Earlier assertions about
unimplemented SPMI channels, a wholly inaccessible channel window and an absent
keypad stack were not established and are corrected in the comparison.

## Sources and hardware data

`source-lock.json` pins Mu and SHA-256 of locally owned stock `uefi.elf`,
`xbl_config.elf` and `boot.img` from
TB520FU_ROW_OPEN_USER_Q00002.0_W_ZUI_17.5.10.362_ST_260719-resigned.
Other firmware releases fail validation until reviewed. Stock binaries are not
redistributed in this repository.

Preparation extracts AARCH64 modules and DEPEX, imports the tablet's XBL maps,
and keeps both Tianma and BOE NT36532 panel resources. The inventory records 71
module/raw entries and 43 memory regions. Qualcomm DiskIoDxe and PartitionDxe
are retained for GPT-record/partition-label protocols. Binary patches require
exact input/output hashes and original bytes.

Original SEC at 0xA7000000..0xA7100000 remains reserved. The new FD occupies
0xA7100000..0xA7400000; the stack is 0xA760D000..0xA764D000. SimpleFbDxe inherits
ABL scanout at 0xD5100000, 2944x1840 BGRA32, stride 2944. Linux uses the selected
external TB520FU DTB. Foreign ACPI, panel data and memory addresses are not imported.

Serial diagnostics are mirrored to the reserved stock ramoops console at
0xA2000000 (2 MiB). DXE entry/exit records remain enabled, with no artificial
per-driver delay. Forced power-off can lose these logs.

## Current adaptations

- ClockDxe omits repeated CESTA initialization and retains clock registration.
- UFSDxe wakes the device WLUN with START STOP UNIT. Tablet captures passed the
  previous readiness ASSERT.
- GICv3 masks and EOIs an unowned interrupt before logging, retaining registered
  handlers and preventing recursive IRQ 0x105 handling from exhausting the stack.
- PmicDxe's cold initialization remains deferred; other code and protocols remain.
- SPMI uses real observer reads and ownership-checked writes. The transfer wrapper
  and data tables remain stock. The pre-command STATUS read is omitted, matching
  Linux transaction ordering; command completion/error polling remains. This is
  a hardware hypothesis, not proof that an owned channel cannot fault after ABL.
  Unowned writes return a vendor error and zero bytes.
- ButtonsDxe maps power to Unicode Enter. Its keypad device path already matches
  the source boot manager. Actual PMIC PON reads need a tablet test.
- UsbConfigDxe selects host mode for core 0 and leaves absent core 1 disabled.
  Host selection does not prove VBUS, switching or USB enumeration.
- TzDxeLA preserves the ABL global-applet handoff. FeatureEnablerDxe returns
  EFI_UNSUPPORTED for the unavailable optional TA. Secure services are unverified.
- RscDxe's camera/PCIe initialization is deferred with EFI_UNSUPPORTED. It is
  separate from the enabled report-status-code router.
- The boot manager fallback opens the menu when no boot target is available.
  The Mass Storage application is included for its registered FV boot option.

Build scripts do not flash or reboot the tablet. No ABL/XBL/TZ partition is
changed. Output is unsigned and requires an already unlocked bootloader.

## Build and checks

Install the pinned project's [dependencies](https://github.com/Project-Silicium/Mu-Silicium/blob/8d73b66ab554f9ab6134b58839bb1e46ebd47688/Building.md),
then run from this repository:

```bash
export STEAMOS_WORK=/work/tb520fu
bash scripts/build-tb520fu-uefi.sh --build-debug /path/to/stock/image
```

`--prepare-only` validates without compiling. `--build` selects RELEASE.
Outputs and provenance are under `$STEAMOS_WORK/uefi/output`.

```bash
python3 tools/check-tb520fu.py --uefi-prepared /path/to/prepared/mu
python3 tools/test-tb520fu-ufs-patch.py --stock /path/to/stock/image
python3 tools/test-tb520fu-gic-handler.py --uefi-prepared /path/to/prepared/mu
# Requires Unicorn 2.1.4; the SPMI test also needs AArch64 GNU binutils.
python3 tools/test-tb520fu-second-stage.py --stock /path/to/stock/image --uefi-prepared /path/to/prepared/mu
python3 tools/test-tb520fu-spmi.py --stock /path/to/stock/image --uefi-prepared /path/to/prepared/mu
python3 tools/compare-tb520fu-uefi.py --reference /path/to/y703/boot.img --stock /path/to/stock/image --built /path/to/Mu-tb520fu.img --uefi-prepared /path/to/prepared/mu --output comparison.json
```

These checks execute ARM64 instructions against simulated MMIO and verify packed
image contents. They do not establish functioning tablet hardware.
Platform templates retain Mu's BSD-2-Clause-Patent notices; see
`LICENSE.Mu-Silicium`. Vendor ownership remains with the respective owners.
