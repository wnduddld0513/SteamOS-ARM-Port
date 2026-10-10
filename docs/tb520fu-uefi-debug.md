# TB520FU UEFI display investigation

The initial RELEASE image produced a black screen with the backlight on. The
first DEBUG image displayed DXE load messages through `ClockDxe.efi` before
turning black. The photo establishes execution through early DXE; it does not
prove that ClockDxe hangs or that it returned. The load message is printed
before the entry point is called.

Read-only TWRP checks on 2026-10-10 identified the Tianma panel, a connected
2944x1840 display, and the stock splash reservation at 0xD5100000. The active
UEFI, XBL configuration and ABL partition prefixes exactly matched the pinned
stock files. No prior UEFI log was present in pstore after an intervening
Android boot.

## Changes

The port had replaced the stock DisplayDxe with SimpleFbDxe. SimpleFbDxe only
publishes an inherited framebuffer; it does not restore a panel or scanout
changed by the stock clock/power drivers. The updated build retains the stock
DisplayDxe and its DEPEX and panel resources. This addresses an incomplete
display handoff, but is not proof of the cause of the observed ClockDxe-stage
black screen. ClockDxe is unchanged; it is neither skipped nor binary-patched.

The TB520FU serial library mirrors diagnostics into the live DT's 2 MiB ramoops
console at 0xA2000000. It uses Linux's DBGC header and ring layout, reserves that
memory in the UEFI map and leaves the adjacent pmsg region untouched. The
framebuffer writer is adapted from the pinned Mu FrameBufferSerialPortLib.
The DXE dispatcher logs `TB520FU DXE ENTER <GUID>` and
`TB520FU DXE EXIT <GUID> Status=<status>` around each entry point. Therefore a
log can distinguish a returned ClockDxe from a stop during its entry point even
when the screen goes dark. Stock driver GUIDs are listed in
[stock-inventory.json](../external-and-mods/tb520fu/uefi/stock-inventory.json).

These source overrides apply only to the dedicated TB520FU Mu checkout. Other
device source files and builders are unchanged.

## Build and validation

Use `scripts/build-tb520fu-uefi.sh --build-debug STOCK_IMAGE_DIRECTORY`.
The diagnostic artifact is separate from the original RELEASE image.
[Build metadata](tb520fu-uefi-debug-build.json) records its hash and checks.

Mu's build completed and verified 49 source-built images. Independent checks
validated Android v4 packing, the exact gzip BootShim/FD payload, dispatcher
trace strings and stock DisplayDxe inclusion without a duplicate SimpleFbDxe.
The host test runs the actual C ring writer in anonymous memory and verifies
Linux readback order, wrapping, invalid headers, interrupt restoration and pmsg
isolation. Static checks preserve the 4,205 original repository files.

Neither the new display path nor persistence through a tablet reset has been
verified on hardware. The existing SteamOS USB image was not rebuilt.

## Temporary boot and log collection

From Windows CMD with the tablet in bootloader mode:

```cmd
fastboot boot "%USERPROFILE%\Documents\TB520FU\install-tb520fu\tb520fu-uefi-cestafix-debug-v8.img"
```

This command boots the image temporarily. Do not flash it to a boot partition.
If it turns black, use the device's recovery key sequence to go directly to
TWRP without booting Android or powering off. Then run:

```cmd
adb devices
adb pull /sys/fs/pstore "%USERPROFILE%\Documents\TB520FU\install-tb520fu\uefi-pstore"
```

The supplied `collect-tb520fu-uefi-log.cmd` collects the same directory and the
current recovery dmesg. It sends no reboot, mount or partition write commands.
A valid `console-ramoops-0` may contain the previous UEFI log. A cold reset,
bootloader memory clearing or another kernel boot can lose it; an empty log
alone cannot prove the UEFI failed before logging.

## Second hardware attempt

The display-restoration image also produced a black screen. Direct recovery
readback found an empty pstore and `found existing invalid buffer, size 223573,
start 485717`. Linux rejects start greater than size; the writer now validates
that invariant before reusing a buffer and publishes size before start. The
regression test covers the observed values. This fixes a diagnostic defect;
it does not establish the cause of the display failure or guarantee RAM
retention across recovery boot.

## Third candidate: observed PMIC/SPMI abort

The v2 readback retained 122943 bytes. Text has bit corruption, so numeric
register values must be treated cautiously. The tail contains a PmicDxe
entry followed by a synchronous exception, an SPMI stack and an ASSERT.
The stock SPMI RVA 0x37F0 is `ldr w9, [x3, x4]`. The PMIC return RVA
0x11D30 follows a call in the init routine at RVA 0x11D14. That routine
starts by writing SID 7 register 0x287F and then performs more PMIC setup.

V3 replaces the first two instructions of that one PMIC init routine with
`mov w0, wzr; ret`. Input SHA-256, original bytes, RVA and resulting SHA-256
are checked before applying it. Stock driver registration, SPMI, ClockDxe
and DisplayDxe remain present. This is a cold-init bypass candidate for an
Android-loader warm handoff, not a general PMIC implementation. Other PMIC
users may still hit protected registers. It has not been boot-tested.

The same-SoC upstream [giulia notes](https://github.com/Project-Silicium/Device-Binaries/blob/main/giulia/README.md)
document PMIC/SPMI crash workarounds, but no foreign-device binary or address
is used here. The current candidate deliberately changes only the locally
identified PMIC init routine; it does not yet implement the paired SPMI
workaround or claim the screen blackout is resolved.

## Fourth candidate: preserve display clock dependencies

The v3 recovery attempt had an empty pstore. On this tablet recovery requires
a forced shutdown followed by fastboot and recovery, so RAM retention cannot
be relied on and an empty pstore does not identify the stop location. The
earlier advice to reach recovery without shutdown was not applicable. V3's
PMIC workaround is still unverified on hardware.

V4 retains the v3 PMIC workaround and adds one four-byte ClockDxe patch:
RVA 0xA810 changes `bl 0xA668` to `mov w0, wzr`. This is the
DCDDisableDependencies call removed in the same-SoC giulia port to keep clocks
on. The unpatched TB520FU routine and its caller at 0xA668..0xA843 are
byte-identical to that reference, whose patched module changes only the call.
No giulia executable is included in the TB520FU image. The patch validates
the full local stock input hash, instruction bytes and output hash.

This candidate aims to preserve inherited scanout so later errors remain
visible. It does not establish that ClockDxe was the only cause of blackout.
Stock DisplayDxe remains included. Earlier sections describe earlier images;
ClockDxe is changed only starting with v4.

## Fifth candidate: inherit the panel scanout

V4 displayed early debug text, changed to solid gray, then entered Qualcomm
CrashDump. The supplied photograph contains ramdump startup messages, UFS
information and `tianma panel`, but no fatal reason or exception address.
`PM: Driver Init # SPMI Transn: 880` is not established as an error code.

V5 changes only the display service relative to v4: source SimpleFbDxe replaces
stock DisplayDxe at its APRIORI position. The clock-dependency and PMIC patches
are retained. SimpleFb publishes the inherited framebuffer without panel or
clock programming. This tests whether the second panel initialization
contributes to the gray screen; it does not prove the CrashDump cause.
The old initial SimpleFb build did not contain either of the later clock/PMIC
workarounds, so its black screen does not settle this combined path.

The current inventory count is 69 stock module/raw entries and 43 regions.
Earlier sections and counts describe earlier candidates. V5 is not yet
verified on hardware. Forced shutdown/recovery may erase RAM diagnostics.

## Sixth candidate: paced diagnostic video

V5 still changed from scrolling debug text to gray. There is no new retained
exception log that establishes which driver caused that transition. V6 keeps
the v5 display, clock and PMIC paths, and adds only a DEBUG-build 250 ms
CoreStall after each DXE ENTER marker, before entering that driver. CoreStall
returns immediately until the metronome architectural protocol is available.
RELEASE builds have no added delay. This is a diagnostic timing change, not
a hardware fix; it can change watchdog or race timing.

Record the tablet from before fastboot boot until the screen changes. The
last readable Loading driver name and DXE ENTER GUID before gray identify
the execution boundary for the next investigation. A final solid-color
photograph alone cannot recover that information. Normal boot of v6 has not
been verified. A blank pstore after forced recovery is inconclusive.

## Seventh image: DEBUG-only ClockDxe isolation

V6 reportedly lost the display immediately after the ClockDxe text. Whether
the EXIT marker appeared is unknown. Independent FV inspection confirmed
that v6 actually contained the expected patched TB520FU ClockDxe bytes.

V7 skips CoreStartImage only for ClockDxe GUID
4db5dea6-5302-4d1a-8a82-677a683b0d29 in DEBUG builds and reports EFI_UNSUPPORTED
with a diagnostic marker. RELEASE builds still execute ClockDxe normally.
All other dispatch behavior and v6 pacing remain unchanged. This is strictly
a display-loss isolation experiment, not an installable firmware fix.
Dependents may wait for missing clock protocols, fail, or assert.

The requested observation is whether text remains visible instead of turning
gray after the skip marker. It cannot demonstrate complete UEFI/OS support.
The skip must be removed or gated off before treating DEBUG as a normal boot.

## Clock investigation after v7: source candidate only

The supplied v6 photo ends at DXE ENTER for ClockDxe GUID
4db5dea6-5302-4d1a-8a82-677a683b0d29. It does not show the EXIT marker,
and does not by itself prove a fatal stop inside ClockDxe. Earlier v2 RAM
logs reached later drivers despite screen loss. The v7 skip has not been
reported tested. The DEBUG-only skip is now removed from source.

The stock init chain is entry 0x1000 -> entry wrapper 0x1144 -> 0x14D0
-> 0x1B44 -> 0x7D78 -> driver init 0x795C. Driver init calls 0xA6F4 at
RVA 0x7D3C; its failure branch references `Clock_InitCESTA failed.` at
0x11F0C. The previously bypassed DCDDisableDependencies call at 0xA810
is inside 0xA6F4. That old patch left the rest of CESTA initialization active.

The source candidate replaces only the CESTA call at 0x7D3C with
`mov w0, wzr`, retaining ClockDxe initialization and protocol registration.
The old inner DCD patch is no longer applied. Full input/output SHA-256 and
original instruction checks guard the replacement. A host transformation
check confirmed that only four bytes differ and that already modified or
incorrect inputs are rejected.

The pinned upstream [onyx notes](https://github.com/Project-Silicium/Device-Binaries/blob/a1501e0c2e642d6ac0d8f52c85af2a67b75a7799/onyx/README.md)
report removing CESTA init to keep display on. Onyx is a different SoC, so
this is supporting precedent, not proof of the TB520FU cause. The same-SoC
giulia notes document the narrower DCD workaround already tried here.
No foreign executable is used.

This candidate has not been compiled or boot-tested. The user's build-stop
instruction remains in effect. Existing v7 images and their metadata remain
unchanged and do not contain this source candidate. A further hardware test
is required before calling this a fix. CESTA-managed clock/power behavior
may be incomplete with this initialization excluded.

## Eighth image: CESTA candidate compiled

After the user requested compilation, the source candidate above was built
as tb520fu-uefi-cestafix-debug-v8.img. Android v4 packing and the exact gzip
BootShim/FD payload were checked. The final FV contains the hash-locked CESTA
ClockDxe, with 0x7D3C bypassed and the original inner DCD call restored.
The DxeCore skip marker is absent; ClockDxe executes normally. SimpleFb and
the existing PMIC workaround remain. DEBUG pacing remains at 250 ms.
This is an experimental image; hardware boot is not yet verified.

## Ninth candidate: device-WLUN wakeup

v8 reached UFSDxe (`0D35CD8E-97EA-4F9A-96AF-0F0D89F76567`) and asserted
at `UFS.c:2168` with `EFI_DEVICE_ERROR`. The photo contains fixed-format
sense data `70 00 02 ... 04 02`: NOT READY, initialization command required.
The stock PE maps this ASSERT to a NULL handle after `ufs_open(0, 0xD0)`
at RVA `0x3E38`, before protocol installation. This is progress past the
previous ClockDxe entry marker, not evidence of working storage.

The device-WLUN open path tests readiness at RVA `0xA468`. Replace its
TEST UNIT READY call and failure branch with `mov w1, #1; bl 0xBAA8`,
issuing START STOP UNIT with active power condition. The following
initialization calls and error checks are preserved; the ASSERT is not
suppressed and UFSDxe is not skipped. The complete open routine matches
the same-SoC Giulia reference byte for byte, and the eight-byte change
matches its published patch. Only locally extracted TB520FU bytes are used.

Reference: [Giulia UFS patch](https://github.com/Project-Silicium/Device-Binaries/blob/a1501e0c2e642d6ac0d8f52c85af2a67b75a7799/giulia/README.md).

This targets the observed not-ready condition. Hardware verification of
UFS and later boot stages remains pending. Previous PMIC, CESTA and
framebuffer workarounds are retained so this test changes one mechanism.

The v9 DEBUG image was compiled and checked against BootShim/FD and all three patched PE hashes. Local artifact: `tb520fu-uefi-ufswakeup-debug-v9.img` (1269760 bytes), SHA-256 `3afb09ef1b37d4a3de61367cae20f96f4b28fb1bfe1e973f2b02038d7a4889b5`. Actual device boot is pending.
