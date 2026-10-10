# TB520FU UEFI port (experimental)

A dedicated Lenovo TB520FU / lapis / SM8650 platform for
[Mu-Silicium](https://github.com/Project-Silicium/Mu-Silicium/tree/8d73b66ab554f9ab6134b58839bb1e46ebd47688).
Only this opt-in device path is changed. Other device builders are untouched.

The v10 tablet video reached the charging driver, then stopped on an SPMI
external abort. It also showed QSEE secure-app and SPSS partition lookup
failures. The v11 DEBUG candidate addresses those paths with second-stage
workarounds and restores Qualcomm partition interfaces. Host tests and image
checks pass; v11 has not been tested on the tablet. GRUB, USB discovery and
Linux entry remain unverified. See the [debugging record](../../../docs/tb520fu-uefi-debug.md).

## Sources and layout

`source-lock.json` pins Mu and SHA-256 of the local stock `uefi.elf`,
`xbl_config.elf` and `boot.img` from
TB520FU_ROW_OPEN_USER_Q00002.0_W_ZUI_17.5.10.362_ST_260719-resigned.
Other firmware releases fail the checks until reviewed.

The preparation script validates ELF/FV/FFS structures, extracts AARCH64
modules and their DEPEX, reads the stock XBL memory/configuration maps and
preserves both Tianma and BOE Lapis NT36532 panel resources. The inventory
contains 71 stock module/raw entries and 43 memory regions. Stock DiskIoDxe
and PartitionDxe retain Qualcomm GPT-record and partition-type protocols
required by SPSS label lookup. Binary patch manifests pin input/output hashes
and exact original bytes. No other device's executable is used.

The first 1 MiB of stock UEFI at 0xA7000000 is reserved for the original SEC
scheduler and DT-extension context. The new FD uses 0xA7100000..0xA7400000;
the stack is 0xA760D000..0xA764D000. SimpleFbDxe inherits ABL scanout at
0xD5100000, 2944x1840 BGRA32 with a 2944-pixel stride. Stock DisplayDxe is
replaced to avoid reinitializing the panel during second-stage bring-up.
Linux uses the selected external Tianma/BOE DTB; no foreign ACPI is installed.

The serial library mirrors diagnostics to the reserved stock ramoops console
at 0xA2000000 (2 MiB), leaving adjacent pmsg memory untouched. DXE entry/exit
records and a DEBUG-only 250 ms pause help locate failures. Forced power-off
may lose these logs; blank recovery pstore is inconclusive.

## Current workarounds and limits

- ClockDxe: omit repeated CESTA initialization, retaining clock registration.
- UFSDxe: wake the device WLUN with START STOP UNIT instead of only testing
  readiness. The v10 video proceeds past the earlier UFS ASSERT.
- GICv3: mask an unowned interrupt and EOI before logging, preserving registered
  handlers. v10 logs IRQ 0x105 once and continues; GLink transport is unverified.
- PMIC/SPMI: pair the minimal-init workaround with the same-SoC transaction
  wrapper bypass. That wrapper performs no hardware I/O; success there is not
  evidence of functional PMIC writes, battery readings or charging.
- TzDxeLA: preserve the ABL global-applet handoff instead of repeating its cold
  initialization. This does not establish a working secure-world ABI.
- FeatureEnablerDxe: explicitly defer the unavailable optional TA with
  EFI_UNSUPPORTED. Its caller records unavailable status and skips gated
  callbacks. Secure features are not claimed enabled.
- SPSS: restore the stock partition interfaces. Actual spunvm mount and data
  access still need tablet verification; no partition is formatted or changed.
- RscDxe: v11 stops visibly at entry before a persistent black screen. Defer
  its camera/PCIe resource-state controller initialization with EFI_UNSUPPORTED
  before protocol registration or hardware access. This isolates a suspected
  second-stage initialization problem; it does not establish its exact cause
  or functional camera/PCIe RSC support. It is unrelated to RscRtDxe, the
  report-status-code router, which remains enabled.

v12 tablet photos reach the boot manager menu with RSC deferred. Linux boot
and USB media operation remain unverified. v13 removes the per-driver debug
delay while retaining traces, and includes the Mass Storage application that
the existing Qualcomm boot-options library registers. v14 makes the power
button report Enter to UEFI consumers instead of SCAN_SUSPEND, so the boot
manager menu can be confirmed without an external keyboard, although the button
still depends on the PMIC PON status path that the earlier PMIC and SPMI
workarounds may have left unreadable.

These are experimental second-stage boot workarounds. Runtime charging,
secure apps, remaining SPMI paths, USB and ExitBootServices need hardware tests.
No ABL/XBL/TZ partition is modified. The output is unsigned and does not unlock
a locked bootloader. Scripts never flash the tablet.

## Build and checks

Use the pinned project's [dependencies](https://github.com/Project-Silicium/Mu-Silicium/blob/8d73b66ab554f9ab6134b58839bb1e46ebd47688/Building.md),
then run from this repository:

```bash
export STEAMOS_WORK=/work/tb520fu
bash scripts/build-tb520fu-uefi.sh --prepare-only /path/to/stock/image
# Or explicitly compile an Android header-v4 gzip image:
bash scripts/build-tb520fu-uefi.sh --build-debug /path/to/stock/image
```

The build writes output and provenance under `$STEAMOS_WORK/uefi/output`.
`--build` selects RELEASE. No build command flashes the image.

```bash
python3 tools/check-tb520fu.py --uefi-prepared /path/to/prepared/mu
python3 tools/test-tb520fu-ufs-patch.py --stock /path/to/stock/image
python3 tools/test-tb520fu-gic-handler.py --uefi-prepared /path/to/prepared/mu
# Requires Unicorn 2.1.4 in the host test environment:
python3 tools/test-tb520fu-second-stage.py --stock /path/to/stock/image --uefi-prepared /path/to/prepared/mu
```

The ARM64 tests exercise the actual patched instructions, the original feature
error path and the TZ guard. They verify containment and explicit unavailable
status, not working hardware. The v11 artifact was also unpacked to verify its
exact BootShim/FD, all stock hashes/DEPEX and compiled core/display PEs.

Platform templates retain Mu's BSD-2-Clause-Patent notices; see
`LICENSE.Mu-Silicium`. Stock ownership stays with vendors. Binaries, test
dependencies, build checkouts and images remain ignored local artifacts.
