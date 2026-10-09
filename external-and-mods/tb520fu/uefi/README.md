# TB520FU UEFI source port (experimental)

This is a separate Lenovo TB520FU / lapis / SM8650 platform for
[Project Silicium Mu](https://github.com/Project-Silicium/Mu-Silicium/tree/8d73b66ab554f9ab6134b58839bb1e46ebd47688).
It does not repurpose a Y700 UEFI binary. Existing SteamOS device support is unchanged.
**Source preparation has run; UEFI compilation and boot have not run. No boot.img exists yet.**

`source-lock.json` fixes the Mu commit and SHA256 of this tablet's stock
`uefi.elf`, `xbl_config.elf`, and `boot.img`. The stock release is
TB520FU_ROW_OPEN_USER_Q00002.0_W_ZUI_17.5.10.362_ST_260719-resigned.
Other firmware releases deliberately fail until their contents are reviewed and locked.

The preparation script parses ELF load segments, checks FV header checksums,
extracts both gzip-compressed FVs, preserves AARCH64 PE modules and their DEPEX,
and reads the actual XBL UEFI memory map. It generates 69 stock hardware/raw
entries, 41 memory regions, the APRIORI/DXE order and the numeric configuration
map. `stock-inventory.json` records hashes and addresses; it contains no blobs.
Two Lapis NT36532 panel XMLs are retained; unrelated panel XMLs are omitted.

The port uses the pinned Lanai SEC support and standard Mu PI/UEFI services.
The first 1 MiB of stock UEFI at `0xA7000000` is kept as `FD Reserved` so
PlatformPeiLib can find the original scheduler and DT-extension context.
The new firmware occupies `0xA7100000..0xA7400000`; its stack is the stock
`0xA760D000` region. ABL's kernel staging starts at `0xA8000000` in the stock map.
This layout follows the same preservation mechanism as Mu's QRD8550 platform,
using **TB520FU addresses and modules** rather than its board blobs.

SimpleFbDxe reuses the ABL-initialized framebuffer at `0xD5100000`, with
2944×1840 BGRA32 and a 2944-pixel stride. Those mode parameters are an initial
port assumption; framebuffer color order/stride, stock SEC context survival,
USB-host init, removable-media discovery and ExitBootServices need hardware checks.
UEFI does not initialize either Linux panel or touchscreen driver; Linux chooses
its Tianma/BOE DTB in GRUB. No foreign ACPI tables are installed.

The stock AVB/Android BDS implementation is replaced by standard Mu BDS in this
experimental second-stage firmware. This is **not** a signed Lenovo update,
and does not unlock a locked bootloader. No ABL/XBL/TZ partition is modified by
these scripts. No flashing commands are included or executed.

From the repository root, source preparation only (no compiler):

```bash
export STEAMOS_WORK=/work/tb520fu
bash scripts/build-tb520fu-uefi.sh --prepare-only /path/to/stock/image
```

For a future build, follow the pinned project's [build dependencies](https://github.com/Project-Silicium/Mu-Silicium/blob/8d73b66ab554f9ab6134b58839bb1e46ebd47688/Building.md),
including its Python requirements, LLVM/CLANGPDB, ARM64 binutils and make. Then:

```bash
bash scripts/build-tb520fu-uefi.sh --build /path/to/stock/image
```

That explicit command compiles Mu/BootShim, packs an Android header-v4 gzip (matching the stock header version)
image, and writes `uefi/output/tb520fu-uefi-boot.img` and provenance metadata.
The SteamOS TB520FU media builder accepts this output after checking source pins
and image hash. It never flashes the image. An unsigned output remains unverified
until a controlled boot and recovery path are established on the actual tablet.
Kernel/OS build validation was intentionally omitted at the user's request.

The platform template is adapted from Mu's QRD8550 source, retaining its
BSD-2-Clause-Patent notices; see `LICENSE.Mu-Silicium`. The preparation/build
scripts are BSD-2-Clause-Patent. Stock module ownership stays with their vendors;
all binaries and build checkouts are local ignored files, not Git contents.
