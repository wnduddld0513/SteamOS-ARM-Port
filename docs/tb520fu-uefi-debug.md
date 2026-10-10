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
fastboot boot "%USERPROFILE%\Documents\TB520FU\install-tb520fu\tb520fu-uefi-displayfix-debug.img"
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
