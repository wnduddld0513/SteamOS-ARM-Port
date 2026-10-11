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

## Tenth candidate: quiesce unowned level interrupts before logging

The v9 photos show repeated `Spurious GIC interrupt: 0x105`, a GLinkDxe
call in the older stock firmware, then dozens of ArmCpuDxe exception-return
frames at RVA `0x1D6C`. SP is `0xA7600F40`, below the configured
`0xA760D000..0xA764D000` stack. The final write fault at `0xA7600F50`
falls in the preserved CPU vector page. ArmGicDxe RVA `0x252C` is the
DebugPrint stack store. These observations support recursive IRQ handling
and stack exhaustion; relaxing vector-page permissions would hide the
consequence without fixing that path. Exact hardware retrigger timing
remains unverified.

The pinned GICv3 handler logs an unowned interrupt before EOI and never
masks its source. The TB520FU preparation patch now disables that source,
then issues EOI, then logs once. Registered handlers, including timer
handlers, retain their original dispatch and EOI ownership. A later
RegisterInterruptSource call can enable a newly owned source normally.
No global IRQ disable, IRQ 0x105 hardcoded filter, stack enlargement or
memory protection relaxation is applied. The GLink transport itself is
not claimed fixed by this containment change.

`tools/test-tb520fu-gic-handler.py --uefi-prepared <mu>` compiles the actual
handler with mocked IRQ registers/logger. The original handler fails the
mask/EOI-before-log assertion; the patched handler passes it and preserves
registered, special and invalid source behavior. The patch is applied only
in the dedicated TB520FU checkout by its preparation script.

The v10 DEBUG image was compiled and verified against BootShim/FD, the compiled GIC driver and all three stock PE patches. Local artifact: `tb520fu-uefi-gicfix-debug-v10.img` (1269760 bytes), SHA-256 `818f49159bd4338808d4011db0ded3d19dfc58f11f011b13785b6a1c6527f8cd`. Actual device boot is pending.


## Eleventh candidate: second-stage PMIC, secure-app and partition handoff

The complete 15-second v10 video reaches ClockDxe/UFS/FAT success, then
reports QSEE and featenabler TA failures, SPSS spunvm lookup failure, one
masked IRQ 0x105 and finally a synchronous external abort inside SPMI.
The fatal path is QcomChargerDxeLA -> PmicDxe -> SPMI, with ELR
0xD1FD87F0, SPMI RVA 0x37F0 (`ldr w9, [x3, x4]`), X3=0x0C500008,
X4=0x27A000 and FAR=0x0C77A008. SP=0xA764B680 remains inside the
configured stack. This is a different fault from v9's stack exhaustion.
The final ArmCpuDxe ASSERT is an exception-handler stop, not CPU init failure.

Three hash-locked changes are made only to locally extracted TB520FU PEs:

- SPMI: pair the earlier PMIC minimal-init workaround with the Giulia
  same-SoC transaction-wrapper workaround at 0x154C. The complete wrapper
  0x154C..0x15FB is byte-identical before patching. It returns zero without
  executing the protected transaction. This contains the observed access;
  it does not provide functioning PMIC writes or verified charging status.
  Other transaction wrappers remain intact and may need separate work.
- TzDxeLA: initialize its local global-applet-loaded flag at 0xE5A8 to 1.
  Both load/start wrappers use this flag to avoid repeating global secure-app
  initialization after ABL. This follows the Onyx approach but derives the
  address from TB520FU disassembly; no foreign executable is included.
- FeatureEnablerDxe: the optional TA acquisition helper at 0x2370 returns
  EFI_UNSUPPORTED rather than attempting failed featenabler_a, featenabler
  and embedded-TA loads. Its original caller records feature status 2 and
  skips gated callbacks. Protocol registration remains. This explicitly
  defers secure feature gates; it does not repair QSEE or claim enabled
  features. ABL scanout is inherited through SimpleFbDxe.

Stock DiskIoDxe and PartitionDxe replace the generic source substitutes.
SPSS label lookup requests Qualcomm GUID fe2555be-d716-4686-b9d0-79db5921b70d
and partition-type GUID protocol 6848de61-eb61-4def-9a8e-3817cbeb8f1c.
Both exist in stock PartitionDxe; the generic Mu driver does not publish
the Qualcomm GPT record interface. Restoring these exact local modules
addresses the missing interface without changing partition contents or
suppressing SPSS errors. Whether spunvm is found and mounted still requires
a tablet test. The inventory now has 71 stock module/raw entries.

The previous Clock CESTA, UFS wakeup, GIC containment, framebuffer and PMIC
patches remain. No new driver is removed, no storage is formatted, and no
memory permissions are relaxed. Other devices' sources remain unchanged.

`tools/test-tb520fu-second-stage.py` runs the actual ARM64 patched code with
Unicorn 2.1.4. It verifies SPMI returns without I/O, the feature helper and
original caller's unavailable path, the TZ guard branch, exact patch scope,
input/double-application rejection, and the restored partition protocols.
These are host checks, not secure-world, charging, filesystem or boot tests.

References: [Giulia paired PMIC/SPMI patches](https://github.com/Project-Silicium/Device-Binaries/blob/a1501e0c2e642d6ac0d8f52c85af2a67b75a7799/giulia/README.md),
[Onyx second-stage TZ flag](https://github.com/Project-Silicium/Device-Binaries/blob/a1501e0c2e642d6ac0d8f52c85af2a67b75a7799/onyx/README.md).


The v11 DEBUG build completed successfully and its final Android-v4 gzip
payload equals BootShim plus the generated FD. All 71 stock module/raw records
and DEPEX hashes match the final compressed FV; ArmGicDxe, DxeCore and
SimpleFbDxe match their compiled PEs. The local artifact is
`tb520fu-uefi-secondstage-debug-v11.img` (1273856 bytes), SHA-256
`1adb98a5956b973b423b25865e33f910adb07cd6cc60b32840aa17a044f324a5`.
The Windows install copy matches. Actual v11 tablet boot remains untested.

## v12: isolate the camera/PCIe RSC initializer

The subsequent v11 tablet screenshots show UFS, SPSS and QcomChargerDxe
returning Success. SPSS now reports two installed FAT filesystems instead of
the previous missing spunvm interface. These entry returns do not prove
working charging, secure features or filesystem contents. USB driver entries
also return Success. The last visible driver is RscDxe, GUID
ea888df7-d431-44af-844c-7b29390f2758, with ENTER and no visible EXIT.
The user reports persistent black output with the backlight still on.

Stock disassembly identifies this as the camera/PCIe resource-state controller,
not the report-status-code router RscRtDxe. Main RVA 0x14E4 installs protocol
3806cdf0-c281-4345-9b1e-49dfb3126923, then calls its initializer for cam at
0x1558 and pcie at 0x1570. That path maps HWIO, enables camera/PCIe clocks,
programs the sequencer and disables camera clocks. The screenshots alone
cannot identify which call stalls, or exclude a later loss of console output.

v12 changes only this module's initializer: eight hash-locked bytes at
0x14E4 return EFI_UNSUPPORTED before protocol registration or hardware access.
It preserves the previous workarounds and explicitly defers this boot-time
service. No other retained stock PE or DEPEX contains the RSC protocol GUID;
this does not exclude dependencies that construct it dynamically. RscRtDxe
remains enabled. This is a controlled diagnostic workaround, not a verified
repair of the internal RSC problem or proof of camera/PCIe operation.

The ARM64 test executes the patched initializer without boot services or MMIO
mapped and verifies EFI_UNSUPPORTED and return to the caller. It also checks
the input hash, exact patch scope, prepared PE and direct protocol consumers.
The DEBUG image still logs driver ENTER/EXIT, so an RSC EXIT with Unsupported
followed by later entries will establish whether deferral advances boot.

The v12 DEBUG build and post-build validation passed. Unpacking its final
Android-v4 gzip payload verifies exact BootShim/FD contents, all 71 stock
module/raw and DEPEX hashes, and compiled ArmGicDxe/DxeCore/SimpleFbDxe PEs.
Artifact: tb520fu-uefi-secondstage-debug-v12.img, 1273856 bytes, SHA-256
2487a692316be7d0c195d46c8db8a55adf87418f08369f89a49ee155c26e6c03.
The Windows install copy matches. Tablet boot has not yet been verified.

## v13: remove tracing delays and include the registered boot application

The v12 tablet photos reach the Project Silicium logo and BootManagerMenuApp
menu, beyond the previous RSC entry. This confirms progress with RSC deferred,
not functional camera/PCIe initialization. USB GPIO enable returns status 7
while the SuperSpeed PHY reports initialization success. Actual USB media
enumeration, input and Linux boot are still unverified.

Remove the DEBUG-only 250000-us dispatcher stall at the user's request; retain
ENTER/EXIT logs. Include QcomPkg/Extra.fdf.inc in the TB520FU FV instead of
only SiliciumPkg/Extra.fdf.inc. Qcom's include adds MassStorage.inf and then
includes the same Silicium apps/resources. The Qcom boot-options library
registers the hidden Mass Storage option, but that application's FV entry
was previously missing. Its existing DSC component remains unchanged.
This fixes that packaging omission without altering another device's files
or automatically launching the storage application.

The v13 DEBUG build and static checks pass. The unpacked final FV matches
all 71 stock entries/DEPEX and compiled core/display PEs, and contains the
MassStorage application at its registered GUID. The dispatcher source has
no 250000-us stall. Artifact: tb520fu-uefi-secondstage-debug-v13.img,
1277952 bytes, SHA-256
33253684871e403938db54b14861f728c97eb269978c1e63499f5e4e460bc655.
The Windows install copy matches. Tablet v13 boot remains untested.

## v14: power button as the boot manager confirm key

The v12 and v13 photos show the boot manager menu with the volume buttons
working and the power button doing nothing: volume moves the highlight, and no
key confirms a selection. ButtonsDxe reports the PMIC PON power button as
SCAN_SUSPEND (0x0102) in the ScanCode field of EFI_INPUT_KEY. The Mu-built
MdeModulePkg/Application/BootManagerMenuApp that this platform launches
(`BootManagerMenu.c:1136-1182`) switches on Key.UnicodeChar first: SCAN_UP,
SCAN_DOWN and SCAN_ESC are handled inside `case CHAR_NULL`, and selection and
boot happen only in `case CHAR_CARRIAGE_RETURN`. ScanCode 0x0102 therefore falls
into `default: break`. The binary patch published for giulia, onyx and nx729j
rewrites the same immediate to ScanCode 0x000D, which the same switch also
discards, so it cannot work on this platform.

v14 instead redirects the power-button branch into the driver's own Enter
epilogue. ButtonsDxe key handling was re-derived before patching: the routine at
0x1B30 is the only caller of the key builder at 0x3AE8 (call site 0x1BF8); the
state-diff routine at 0x19C8 turns button state changes into a pressed array
(0x8000+0x2A4, count 0x8000+0x278) and a released array (0x8000+0x2C0, count
0x8000+0x27C) that hold key-map indices; the builder maps those entries to key
codes and both the volume buttons and the power button flow through it. The
branch at RVA 0x3CC0 is the only instruction in the whole 0x7000-byte .text that
can produce 0x0102, and it is taken when the first pressed entry is key-map
index 1, which is the power button. The patch replaces the 8 bytes at RVA
0x3CC0 (`mov w8,#0x102` and its unconditional branch) with `b 0x3C74` and a
NOP, so the branch enters `mov w8,#0xD` and `strh w8,[x29,#26]` and then
notifies the event through the driver's normal path at 0x3C90. UnicodeChar
becomes 0x0D while ScanCode stays at the zero it was initialized to, which is
exactly the keystroke the menu accepts and the key code every other UEFI
consumer sees.

A power press only reaches this code if the PMIC PON status path reports it,
because the button is sampled through PmicPONProtocol. The PmicDxe and SPMI
workarounds may leave that status unreadable. If the button still does nothing
in v14, the next step is restoring that path rather than changing another key
code.

The v14 DEBUG build and static checks pass. All eight patched modules on disk
match the hash in their patch record. The uncompressed
Build/tb520fuPkg/DEBUG_CLANGPDB/FV/FVMAIN.Fv contains the patched bytes exactly
once and the stock bytes zero times, and the final image's gzip payload is
byte-identical to the built BootShim/FD payload. Artifact:
tb520fu-uefi-powerkey-debug-v14.img, 1277952 bytes, SHA-256
d695e1a109fb6e1ebf5caee4c81acf6a8219ca55f11ded588ac64f49ed9a756e.
The Windows install copy and powerkey-debug-v14.json match. Tablet v14 boot and
the power button are untested.

```cmd
fastboot boot "%USERPROFILE%\Documents\TB520FU\install-tb520fu\tb520fu-uefi-powerkey-debug-v14.img"
```

The same photos contribute one USB observation. The v13 console shows
`Failed to enable GPIO status : 0x7` for the codec-shared
usb_shared_wcd_usb_switch_reset while `ssusb_phy_init_success lane: 0x0` reports
PHY success, and the captured console tail ends at BootManagerMenuApp. Whether
XhciPciEmulation reported `Unable to configure USB in host mode`, which would
explain silent USB media failure, lies outside the captured region. That line is
the first thing to look for on the next boot, together with a TWRP pstore pull,
because the ramoops console retains the full dispatcher trace.

## v15: drop keystrokes queued before the boot menu is ready

v14 delivered the power button as Enter, but the tablet showed the exception
screen instead of the menu. The delivered Enter was consumed the moment
BootManagerMenuApp started reading input, and the app clears the screen and boots
the highlighted entry (the first registered option, "Internal Storage"), which
faulted. What the screen showed was the cleared console plus the ArmCpuDxe
assert, not a menu that failed to draw.

ButtonsDxe emits at most one key event per press-release cycle. The latch at
0x8000+0x4E0 is set when the key builder runs (RVA 0x3C08) and cleared only when
the pressed count returns to zero (0x3CC8 and 0x3CD4), while 0x3B20 skips the
builder while the latch is set. A power button that the stubbed PMIC reports as
pressed once therefore produces exactly one stale Enter, and a later real press
produces no event until the release is observed.

v15 adds a keystroke drain to
Mu_Basecore/MdeModulePkg/Application/BootManagerMenuApp/BootManagerMenu.c after
the menu is drawn and before the wait loop. It is recorded as
patches/bootmenu-drain-keys.patch and applied by the prepare script, so any key
queued before that point is discarded and a latched press cannot confirm the
highlighted entry. The power button then has to be pressed after the menu is up.

The v15 DEBUG build and static checks pass, and the module was rebuilt in this
run. Artifact: tb520fu-uefi-drainkeys-debug-v15.img, 1277952 bytes, SHA-256
572ddfe7ddd2ba0b62c82a187d54fbcdf54cecc5f9459a94cd1ffe68fc41e4ea.
The Windows install copy and drainkeys-debug-v15.json match. Tablet v15 boot is
untested. If the menu appears and the power button still does nothing, the PMIC
PON status path is not reporting the press, and restoring that path is the next
step rather than another key-code patch.

## v16: keep the fault registers on screen

The v14 and v15 crash screens show only the tail of the exception dump. The
handler in Mu_Basecore/UefiCpuPkg/Library/CpuExceptionHandlerLib/AArch64/CpuExceptionHandlerLib.c
already prints SP, ELR, SPSR, ESR and FAR, but it does so before the 128 byte
stack dump, so those lines have scrolled off the panel by the time the tablet
stops, and this device cannot hand back a ramoops log because a forced reboot
always goes through fastboot and recovery.

v16 repeats the ESR, EC, FAR, ELR and SP line after the stack dump and before
LogToConsole, recorded as patches/except-fault-line.patch and applied by the
prepare script. The last line of the next crash screen therefore carries the
faulting address even in a single photograph.

## v17: stub the SPMI entry point

The v16 line reads ESR 0x96000010 (EC 0x25 data abort at the same exception level,
DFSC 0x10 synchronous external abort), FAR 0x000000000C777008 and ELR
0x00000000D1F317F0. FAR is the SPMI channel window 0x0C500000 plus 0x277 << 12 plus
8, and ELR is the SPMI.efi instruction at RVA 0x37F0 that builds that address; the
v10 family fault was the same instruction with channel 0x27A and FAR 0x0C77A008.
The arbiter implements no such channel, so the read is rejected.

The previous spmi-second-stage site only neutered one internal wrapper. v17 moves
the site to the SPMI DXE entry point (RVA 0x1000, before 1f0000f1c0050054, after
e0031f2ac0035fd6) so the driver never initialises and can never compute a channel
address; PmicDxe already returns before its own init sequence. Expected result: the
boot manager menu appears and the volume keys navigate it. The power button and USB
VBUS stay inert until the PMIC/SPMI path is restored on purpose.

## v18: stop the SPMI channel execute path without hiding the SPMI protocol

The v17 entry-point stub removed the abort but produced a new failure: with the
DXE entry stubbed the driver installs no protocols, so PmicDxe's SPMI-lite
wrapper prints "Locate protocol failed", then "ERROR: C90000002:V03000007 IO
5776232E-082D-4B75-9A0E-FE1D13F7A5D9", then asserts in pm_comm_spmi_lite.c +66.
The v17 console also confirms the original diagnosis: SPMI.efi loads at
0x000D1F2E000 with entry point 0x000D1F2F000, so the faulting ELR
0x00000000D1F317F0 is exactly RVA 0x37F0 inside SPMI.efi.

v18 restores the stock DXE entry point (RVA 0x1000) so SPMI installs its
protocols, and stubs the one routine that builds the channel address read by the
faulting load. Disassembly of the stock module puts that routine at RVA 0x3668
(before ff8303d1fd7b08a9, sub sp, sp, #0xe0 / stp x29, x30, [sp, #128]); its
faulting ldr w9, [x3, x4] is at RVA 0x37F0, and its only caller is the single
bl 0x3668 at RVA 0x2940 inside the function at 0x27e4, which branches to its
error path at 0x294c when the call returns non-zero. v18 replaces that routine
entry with mov w0, wzr ; ret (after e0031f2ac0035fd6), so every transfer reports
success without touching the arbiter. Success rather than an error status is
deliberate: PmicDxe's pm_comm_spmi_lite wrapper asserts readily on a failed
transfer, and a non-zero return would risk replacing the abort with another
assert. The cost is that transfers through this routine are now silent no-ops
(reads hand back whatever the caller's buffer already held, writes are dropped),
so PMIC data must not be trusted yet. The earlier 0x154c wrapper site is dropped,
so the wrapper and the rest of the driver are stock again.

patches/spmi-second-stage.json now carries a sites array with that single entry,
and patch_stock_pe in scripts/prepare-tb520fu-uefi.py applies sites in order while
single-site manifests keep working. The earlier v18 record in this file (site RVA
0x3748, before b44101a9761300f9, artifact 026d8722..., commit e349b9b) came from
work that a workspace rollback discarded, and its site does not exist in this
module at all: b44101a9761300f9 occurs nowhere in the stock PE and RVA 0x3748
holds 4a15098b6b014491 in the middle of the routine. That address belongs to
another module variant and must not be reused here.

Verification for this build: the stock blob hashes to fd6b11d1...65f and the
patched blob to ce798bc4...96f, both asserted by the manifest; running
patch_stock_pe on a reconstruction of the stock blob reproduces the built module
byte for byte; and the built FV's SPMI section (Build/tb520fuPkg/DEBUG_CLANGPDB/
FV/Ffs/2a7b4bef-80cd-49e1-b473-374ba4d673fcSPMI/2a7b4bef-80cd-49e1-b473-374ba4d673fcSEC2.1.pe32)
carries 1f0000f1c0050054 at module RVA 0x1000 and e0031f2ac0035fd6 at module RVA
0x3668, while the faulting 696864b8 is still present at RVA 0x37f0 and
unreachable.

Artifact: tb520fu-uefi-spmi-stub-debug-v18.img, 1277952 bytes, SHA-256
57066f2502b61ad5585d178d75a8fb4d701ed60ea5feac97686aad8939cc5c40, DEBUG, Mu
commit 8d73b66ab554f9ab6134b58839bb1e46ebd47688. Tablet v18 boot is untested. If
the next screen shows neither an ESR line nor the "Locate protocol failed" /
pm_comm_spmi_lite assert, the SPMI abort path is closed and the PMIC work can
resume on top of it.
## v19: reject the channels the arbiter does not implement

The v18 tablet boot answered the v18 question and raised a worse one. No ESR
line and no pm_comm_spmi_lite assert appeared, so the abort path was closed, but
the console also shows "SetupKeypad: Failed to Locate STI Device Path! Status =
Not Found", no boot manager menu at all, "No handles survived filtering!" for the
USB attempt and "[Bds] Unable to boot!" afterwards. That is exactly what this
file warned about in v14: the buttons are sampled through the PMIC PON status
path, so while the SPMI workaround keeps that path dead there are no key events
and therefore no menu. The v15 and v16 photographs still showed the menu with
working volume keys, i.e. input worked as long as SPMI still executed.

v19 therefore restores the driver completely - stock DXE entry at RVA 0x1000 and
the stock prologue of the channel routine at RVA 0x3668 - and moves the guard to
the protocol lookup that produces the channel index the faulting load uses.

The chain is: the single caller at RVA 0x27e4 calls the lookup at RVA 0x3578 with
the PPID index and the transaction class; a successful lookup stores a 16 bit
channel value through the caller's x4 pointer and returns 0, a failed lookup
returns 0x1c (28) and the caller branches to its error path at 0x294c without
ever touching the arbiter. Only on success does it reload that channel from the
stack (ldurh w4, [x29, #-8]) and call the routine at 0x3668, where the address
becomes 0x0C500008 + (context[68] + channel) << 12 - 0x0C777008 for channel 0x277,
the FAR the v16 line recorded. The stock lookup rejects only bit 10
(RVA 0x3584, tbnz w11, #10, 0x35dc -> return 28), so a channel value of 0x277 or
0x27A is accepted even though the arbiter implements no such window.

The per-EE context behind context[68] lives at .data 0x7160 (EE 0) and 0x71a8
(EE 1), 72 bytes each: [0] arbiter base 0x0C400000, [16] EE index, [24] the
PPID to channel table, [32] the node table, [48] a record whose first halfword is
the entry count (0x380 = 896 for EE 0, 0x80 = 128 for EE 1) and [68] the EE
channel base (0 for EE 0, 0x380 for EE 1). Both channel tables are all zero in
the file and are built at runtime from the arbiter, which is why the bad entry
exists only after initialisation. Because context[68] is added before the shift,
masking the computed offset to 0x1ff would mis-address every EE 1 access, so the
guard has to sit in the lookup, not at the point of use.

The v19 site is RVA 0x3598 (before eb030b2a4c696c38, mov w11, w11 / ldrb w12,
[x10, x12]; after 2b0248374c696c38, tbnz w11, #9, 0x35dc / ldrb w12, [x10, x12]).
The replaced mov w11, w11 is redundant: w11 is already zero extended by the ldrh
at 0x3580 and by the and w11, w10, #0x7ff at 0x35d0, and only its low half is
stored at 0x35b0. Together with the stock bit-10 test this rejects every channel
value of 0x200 or above, so the lookup returns 28 (EFI_UNSUPPORTED) and the caller
takes its error path without ever computing or reading an arbiter address. The
node-chain walk jumps back to 0x3590, so a value found deeper in a chain is
tested by the same instruction. Every provisioned PMIC channel is below 0x100, so
real transfers keep their stock behaviour and the PMIC PON path should come back
with them.

Verification for this build: the manifest re-derives the stock blob from the
built module and asserts fd6b11d1...65f before patching; the patched module is
b9cb297b...de1; and the built FV's SPMI section
(Build/tb520fuPkg/DEBUG_CLANGPDB/FV/Ffs/2a7b4bef-80cd-49e1-b473-374ba4d673fcSPMI/
2a7b4bef-80cd-49e1-b473-374ba4d673fcSEC2.1.pe32, whose raw offsets run four bytes
ahead of the module RVAs) carries 1f0000f1c0050054 at the DXE entry,
2b0248374c696c38 at RVA 0x3598, the stock prologue ff8303d1fd7b08a9 at RVA 0x3668
and the faulting 696864b8 still present but unreachable at RVA 0x37F0.

Artifact: tb520fu-uefi-spmi-guard-debug-v19.img, 1277952 bytes, SHA-256
65e92bb5451d30624993806fd58ca32c17e6dec9c6c69aa28b20ab201a358dd3, DEBUG, Mu
commit 8d73b66ab554f9ab6134b58839bb1e46ebd47688. Tablet v19 boot is untested.
Expected on the next boot: the boot manager menu returns with working volume
keys, the power button confirms through the v14 redirection, USB VBUS comes back,
and a transfer to an unimplemented channel returns EFI_UNSUPPORTED instead of
aborting.

## USB host mode: what this platform already ships

Recorded while tracing the "USB boot desired, but no USB devices found" line, so
the same ground is not re-covered. The DXE and APRIORI lists of this port already
carry the full vendor USB set, in the same order as the only other SM8650
platform in the tree (Platforms/OnePlus/giuliaPkg, OnePlus 13R / Ace 5):

  UsbPwrCtrlDxe, UsbfnDwc3Dxe, XhciPciEmulationDxe, XhciDxe, UsbBusDxe,
  UsbKbDxe, UsbMassStorageDxe, UsbMsdDxe, UsbDeviceDxe, UsbConfigDxe, UsbInitDxe

in Platforms/Lenovo/tb520fuPkg/Include/DXE.inc lines 73-86 and APRIORI.inc lines
64-73. Both the host path (XhciPciEmulationDxe plus XhciDxe) and the device path
(UsbfnDwc3Dxe, UsbDeviceDxe) are present, and no USB related PCD is defined
anywhere in tb520fuPkg or Silicon/Silicium/SiliciumPkg, so the role is not chosen
by this port's configuration. giuliaPkg, which lists the same drivers, still
reports "USB Host Mode" as unsupported in its Status.md, so the difference is not
a missing driver either.

The role is decided inside the prebuilt vendor blobs. UsbConfigDxe.efi (90112
bytes, SHA-256 c56a7783d544d0b1446c5add31c94dd8d8baa9db75b8201b57fb45dc04a3c253)
contains both paths and their own events: "ConfigUsb: Error - failed to perform
common initialization for USB core %d: %r", "... failed to perform device
initializaition for USB core %d: %r", "... failed to perform host initializaition
for USB core %d: %r", plus "Failed to Create ToggleUsbModeEvent" and "Failed to
Create ConfigUsbEvent". XhciPciEmulation.efi (40960 bytes, SHA-256
5d13057ccd32e6c475be19536f8c8f43c07f9e4e98aa1fd1178315e92869a941) prints
"Unable to configure USB in host mode, Status = (0x%x)"; that line is the first
thing to look for on the next boot, because the v13 capture ended at
BootManagerMenuApp and never covered it. The other recorded USB lines are
"Failed to enable GPIO status : 0x7" for usb_shared_wcd_usb_switch_reset while
"ssusb_phy_init_success lane: 0x0" reports PHY success.

The other two driver hashes are UsbPwrCtrlDxe.efi (40960 bytes, 42d32f9b5be6f1
56909721de2e401ac47b9401fa12ca2aa4fa1c9a18e07cda9c) and UsbMsdDxe.efi (61440
bytes, bdf09fed17e3d70d6f10a48110760c0b18d6feae4a3bbcc0327e2f0683443b17); all
four are stock, because no patch manifest targets them yet. This matches the
public Mu-Silicium answer on issue #1619: host mode cannot be enabled by
configuration, only by building a different (dual role) UsbConfigDxe, which is
what the Device-Binaries dual role patches (UsbConfigDxe.patched.efi,
UsbMsdDxe.patched.efi, UsbPwrCtrlDxe.patched.efi, PR #68) do by hand. Any fix on
this platform therefore has to be a byte patch to those blobs, applied through the
same sites array as every other module patch, not a change to the DXE lists.
