# TB520FU and the working Y703 boot image

Recorded 2026-10-12. The supplied reference is
`steamos-arm-port-lenovo-legion-y700-gen3-internal-v1.3.0-test7/boot.img`,
SHA-256 `45f923bc3980a8ba6e12ce606c30b4b08c2de48047626648a3d1861c95d2a58f`.
Only the boot image was inspected; super/userdata images were not altered.
The [comparison JSON](tb520fu-y703-comparison.json) is reproduced by
`tools/compare-tb520fu-uefi.py` from local firmware without redistributing it.

## What differs

| Item | Working Y703 reference | TB520FU v21 |
| --- | --- | --- |
| Android boot header | v3, padded to 96 MiB | v4, 1,277,952 bytes |
| Gzip payload | 112-byte BootShim + 4 MiB FD | 112-byte BootShim + 3 MiB FD |
| FD destination | 0xF3800000 | 0xA7100000, from TB520FU XBL map |
| Parsed FFS entries / named PE modules | 201 / 141 | 118 / 107 |
| UI/input | Older Mu MSUI BootMenu, HID keyboard/mouse and virtual keyboard | BootManagerMenuApp and UsbKbDxe |
| SPMI bus geometry | 768 + 256 APIDs | 896 + 128 APIDs, confirmed in TWRP |
| SPMI transfers | Functional stock code | Functional stock code plus owner/ordering guard |
| Panel and power data | Y703 | TB520FU Tianma and BOE resources, inherited ABL scanout |

Header version, padding and total driver count do not explain a dead keyboard.
TB520FU already executes DXE and displays a menu. Copying the reference's 96 MiB
padding, RAM destination, ACPI or panel data would not make device-specific
initialization correct for this tablet. The older MSUI graphics/HID stack is a
real UI difference, but it cannot repair a USB controller that has not enumerated
the dongle. Exact source revision/provenance cannot be recovered from a lone
compiled image; this work does not claim to reproduce its unknown build tree.

Reference SPMI `.text` is 24,576 bytes and byte-identical to TB520FU stock.
ButtonsDxe `.text` is 28,672 bytes and also byte-identical. The reference has
neither of our successful no-op SPMI stubs. Its data tables differ, so executable
equality does not authorize copying whole modules. The reference's power key
still generates SCAN_SUSPEND; v21 retains Unicode Enter because the current boot
manager expects that confirmation key.

The reference omits some drivers stock TB520FU carries, including RscDxe,
QcomChargerDxeLA and ChargerExDxe. This establishes different firmware/platform
integration, not that tablet power dependencies can be removed wholesale.
The source-built service and hardware-data split is retained. The new image was
compiled in a separate directory with no previous Build outputs; it is a new
build of the TB520FU platform, not a renamed or transplanted Y703 binary.

## TWRP findings and corrections to earlier explanations

ADB was connected to TB520FU recovery. The live DT and loaded
`spmi-pmic-arb.ko` were read. Temporary kprobes read already-mapped kernel values;
they were disabled and removed afterward. Regmap address/count selectors were
restored. No PMIC register writes, partition writes or reboot were issued.

| Observation | Value |
| --- | --- |
| Arbiter version | 0x70010000 (v7) |
| FEATURES0 / FEATURES1 | 0x80060380 / 0x00000080 |
| Application processor EE | 0 |
| Bus 0 base / count | 0 / 896 |
| Bus 1 base / count | 896 / 128 |
| APID 0x4c mapping / write owner | PPID 0x183 / EE 4 |
| APID 0x277 mapping / write owner | PPID 0x021 / EE 0 |
| Physical USB controller | One DWC3 at 0x0A600000, OTG in live DT |

This supersedes the v19 claim that every channel above 0x1ff is invalid.
Channel 0x277 is implemented. TB520FU stock geometry matches the live kernel;
Y703 geometry would be wrong here.

The v19 fault at `SPMI+0x37f0`, FAR `0x0C54C008`, accessed the write channel for
APID 0x4c even though it belongs to EE 4. The stock lookup can return a matching
SID/APID with success after failing its owner comparison and reaching the end of
the linked chain. v21 checks the selected node again before any write MMIO and
returns vendor result 28 with zero transferred bytes on owner mismatch.
Observer reads remain allowed across write ownership, matching Linux behavior.

The older fault at `0x0C777008` was on AP-owned channel 0x277. Ownership alone
does not explain that fault. The v20 assertion that the entire channel window
must be inaccessible, or that a UEFI-side change cannot help, was too strong.
Linux starts a transfer by writing WDATA/CMD and then polling STATUS. The vendor
code pre-reads STATUS at 0x37f0. v21 removes only that preflight read and retains
normal post-command completion/error polling. Command-first ordering is an
explicit hypothesis for the remaining fault and needs a tablet boot test.
Host emulation verifies ordering, not tablet firewall/clock state.

The v20 claim that the keypad stack is absent was also too strong. Stock
ButtonsDxe includes the same `D7F58A0E-BED2-4B5A-BB43-8AB23DD0E2B0` vendor path
the source BDS expects, and installs STI/STIEx/device-path protocols. A failed
LocateDevicePath establishes an unavailable input interface at that time, not
a need for foreign KeypadDxe. Real PMIC reads are restored before considering
a replacement input stack.

## v21 changes and validation

SPMI wrapper 0x154c is restored. The raw transfer entry 0x3668 branches into
128 bytes of unused executable padding at 0x6f00. The guard validates the relative
APID against the stock bus count, rejects unowned writes and resumes the original
prologue at 0x3670. The preflight instruction at 0x37f0 becomes `mov w9,#1`.
Data tables, relocations and all other code remain stock. The exact assembly,
original bytes and hashes are committed with the manifest.

UsbConfigDxe sets only the real core-0 mode byte to host. v20 had also enabled
absent core 1; that extra byte is now stock zero. The existing host-start argument
1 and power-to-Enter patch remain. Per-driver delays remain removed.
Clock/UFS/GIC/display adaptations that passed earlier tablet stages are retained.
PMIC cold initialization and camera/PCIe RSC initialization remain deferred, and
secure-service support remains unverified.

Validation passed:

- Fresh DEBUG/CLANGPDB full UEFI build; Mu validated 49 source PE images.
- Actual ARM64 SPMI guard/transfer emulation: owner mismatch performs no MMIO;
  reads and owned writes move buffer data; both bus layouts, chunking,
  command-first order, timeout and error propagation are exercised.
- Assembly is reassembled and linked at its actual RVA to verify exact bytes.
- Power emits Unicode Enter; the USB mode switch selects core-0 host and passes
  the expected start argument.
- Existing UFS, GIC, secure-feature and partition protocol checks pass.
- All 71 module/raw hashes and DEPEX match inside the packed FD. The gzip payload
  exactly matches the fresh BootShim and FD. Original device builders are preserved.

Local artifact: `install-tb520fu/tb520fu-uefi-y703-baseline-debug-v21.img`.
SHA-256: `f99bf4c85845872083bc26d79e7a11fc18e89916671d9943772bde8966752d3d`.
This candidate is not yet hardware-tested. A remaining owned-channel abort, PMIC
client failure, WCD switch GPIO error or missing USB VBUS requires further
hardware evidence; no successful Linux boot is claimed.

From either Windows CMD or PowerShell, manually test without flashing:

```text
fastboot boot "C:\Users\HJY\Documents\TB520FU\install-tb520fu\tb520fu-uefi-y703-baseline-debug-v21.img"
```
