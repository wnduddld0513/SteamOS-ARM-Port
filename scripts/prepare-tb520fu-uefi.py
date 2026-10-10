#!/usr/bin/env python3
"""Prepare the TB520FU Mu platform from locally owned stock firmware; no compilation.

Bounded ELF/FV/FFS parsing, gzip extraction, and DTB parsing use only Python stdlib.
No stock binaries are redistributed by this repository.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import gzip
import hashlib
import json
import re
import shutil
import struct
import subprocess
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PORT = REPO / "external-and-mods/tb520fu/uefi"
LOCK = json.loads((PORT / "source-lock.json").read_text())
APRIORI = "fc510ee7-ffdc-11d4-bd41-0080c73c8881"
GZIP = "1d301fe9-be79-4353-91c2-d23bc959ae0c"


def need(ok, message):
    if not ok:
        raise ValueError(message)


def patch_stock_pe(name, pe):
    """Apply hash-locked workarounds to locally extracted TB520FU modules."""
    manifests = {"PmicDxe": "pmic-warm-boot.json", "ClockDxe": "clock-display-handoff.json"}
    if name not in manifests:
        return pe, None
    manifest = json.loads((PORT / "patches" / manifests[name]).read_text())
    need(hashlib.sha256(pe).hexdigest() == manifest["input_sha256"],
         "stock PE patch input does not match the reviewed build")
    hdr = struct.unpack_from("<I", pe, 0x3c)[0]
    count = struct.unpack_from("<H", pe, hdr + 6)[0]
    table = hdr + 24 + struct.unpack_from("<H", pe, hdr + 20)[0]
    rva = int(manifest["rva"], 0)
    before, after = bytes.fromhex(manifest["before"]), bytes.fromhex(manifest["after"])
    matches = []
    for i in range(count):
        _, va, size, offset = struct.unpack_from("<IIII", pe, table + 40 * i + 8)
        if va <= rva and rva + len(before) <= va + size:
            matches.append(offset + rva - va)
    need(len(matches) == 1, "stock PE patch RVA is not uniquely file-backed")
    offset = matches[0]
    need(pe[offset:offset + len(before)] == before, "stock PE patch instruction mismatch")
    result = pe[:offset] + after + pe[offset + len(before):]
    need(hashlib.sha256(result).hexdigest() == manifest["output_sha256"],
         "stock PE patch output hash mismatch")
    return result, manifest


def guid(data):
    return str(uuid.UUID(bytes_le=data))


def sections(data):
    pos = 0
    while pos + 4 <= len(data):
        size = int.from_bytes(data[pos:pos + 3], "little")
        kind = data[pos + 3]
        need(4 <= size <= len(data) - pos, "invalid section length")
        yield kind, data[pos + 4:pos + size]
        pos = (pos + size + 3) & ~3


def files(data):
    need(data[40:44] == b"_FVH", "invalid FV signature")
    length = struct.unpack_from("<Q", data, 32)[0]
    pos = struct.unpack_from("<H", data, 48)[0]
    need(pos <= length <= len(data), "invalid FV bounds")
    need(sum(struct.unpack_from("<" + "H" * (pos // 2), data)) % 65536 == 0,
         "invalid FV header checksum")
    while pos + 24 <= length:
        pos = (pos + 7) & ~7
        head = data[pos:pos + 24]
        if head == b"\xff" * 24:
            break
        size = int.from_bytes(head[20:23], "little")
        need(24 <= size <= length - pos and size != 0xffffff, "invalid FFS bounds")
        if head[18] != 0xf0:  # Pad files have no section stream.
            yield guid(head[:16]), head[18], list(sections(data[pos + 24:pos + size]))
        pos += size


def volumes_from_elf(data):
    need(data[:5] == b"\x7fELF\x02", "expected TB520FU ELF64 container")
    phoff = struct.unpack_from("<Q", data, 32)[0]
    entsize, count = struct.unpack_from("<HH", data, 54)
    need(entsize == 56 and count <= 16, "unexpected ELF program headers")
    load = []
    for i in range(count):
        kind, flags, off, virt, phys, size, mem, align = struct.unpack_from("<IIQQQQQQ", data, phoff + i * entsize)
        if kind == 1:
            need(off + size <= len(data), "ELF load outside input")
            load.append((phys, data[off:off + size]))
    need(len(load) == 1 and load[0][0] == 0xa7000000, "unexpected stock UEFI load region")
    outer = list(files(load[0][1]))
    result = list(outer)
    for ident, kind, sect in outer:
        for ty, payload in sect:
            if ty != 2:
                continue
            need(guid(payload[:16]) == GZIP, "unexpected stock FV compression")
            offset, flags = struct.unpack_from("<HH", payload, 16)
            need(offset == 24 and flags == 1, "unexpected GUID section header")
            decoded = gzip.decompress(payload[offset - 4:])
            need(len(decoded) <= 32 * 1024 * 1024, "oversized stock FV")
            nested = [v for t, v in sections(decoded) if t == 0x17]
            need(len(nested) == 1, "expected one nested firmware volume")
            result.extend(files(nested[0]))
    return result


def dt_nodes(data):
    need(data[:4] == b"\xd0\x0d\xfe\xed", "invalid DTB")
    total, off, strings_off = struct.unpack_from(">III", data, 4)
    strings_size, struct_size = struct.unpack_from(">II", data, 32)
    need(total <= len(data) and off + struct_size <= total and strings_off + strings_size <= total,
         "invalid DTB bounds")
    strings = data[strings_off:strings_off + strings_size]
    pos, stack, nodes = off, [], []
    while pos < off + struct_size:
        token = struct.unpack_from(">I", data, pos)[0]; pos += 4
        if token == 1:
            end = data.index(0, pos); name = data[pos:end].decode()
            pos = (end + 4) & ~3
            stack.append(name); nodes.append(("/".join(stack), {}))
        elif token == 2:
            stack.pop()
        elif token == 3:
            length, nameoff = struct.unpack_from(">II", data, pos); pos += 8
            need(nameoff < len(strings) and pos + length <= off + struct_size, "DTB property bounds")
            name = strings[nameoff:strings.index(0, nameoff)].decode()
            path = "/".join(stack)
            target = next(props for p, props in reversed(nodes) if p == path)
            target[name] = data[pos:pos + length]; pos = (pos + length + 3) & ~3
        elif token == 9:
            return nodes
        else:
            need(token == 4, "invalid DTB token")
    raise ValueError("DTB has no end token")


def memory_map(xbl):
    maps = []
    start = 0
    while (start := xbl.find(b"\xd0\x0d\xfe\xed", start)) >= 0:
        total = struct.unpack_from(">I", xbl, start + 4)[0]
        try:
            nodes = dt_nodes(xbl[start:start + total])
            items = [(path, p) for path, p in nodes if "MemLabel" in p and
                     ("/memorymap/" in path or "/registermap/" in path)]
            if items:
                maps.append(items)
        except (ValueError, IndexError, struct.error):
            pass
        start += 4
    need(len(maps) == 1, "expected one unambiguous XBL UEFI memory map")
    output = []
    hob = {0: "AddMem", 4: "NoHob", 5: "AddDev", 9: "HobOnlyNoCacheSetting", 10: "HobOnlyNoCacheSetting"}
    cache = {2: "WRITE_BACK", 0x22: "WRITE_BACK_XN", 0x20: "WRITE_THROUGH_XN", 0x25: "UNCACHED_UNBUFFERED_XN", 9: "NS_DEVICE"}
    for path, props in maps[0]:
        name = props["MemLabel"].rstrip(b"\0").decode()
        address, length = struct.unpack(">QQ", props["reg"])
        raw = {k: int.from_bytes(props[k], "big") for k in
               ["ResourceAttribute", "BuildHob", "ResourceType", "MemoryType", "CacheAttributes"]}
        need(raw["BuildHob"] in hob and raw["CacheAttributes"] in cache, "unknown memory attributes")
        # Stock SEC and its scheduler must remain intact for PlatformPeiLib's
        # GetXblHobAddresses(). The custom image occupies the remaining 3 MiB.
        regions = [(name, address, length)]
        if name == "UEFI_FD":
            need((address, length) == (0xa7000000, 0x400000), "unexpected UEFI FD")
            regions = [("FD Reserved", address, 0x100000), (name, 0xa7100000, 0x300000)]
        # Keep the verified stock ramoops console reserved and CPU-accessible.
        # The original PIL reservation covers it with no cache mapping.
        # A SYSTEM_MEMORY resource with EfiReservedMemoryType emits an allocation
        # HOB, so RamManagerDxe cannot add the console to its usable page pool.
        if name == "PIL_Reserved":
            log_base, log_size = 0xa2000000, 0x200000
            need(address <= log_base and log_base + log_size <= address + length,
                 "ramoops console outside PIL reservation")
            regions = [(name, address, log_base - address),
                       ("TB520FU_Ramoops", log_base, log_size),
                       ("PIL_Reserved_Tail", log_base + log_size,
                        address + length - log_base - log_size)]
        for label, addr, size in regions:
            output.append({"name": label, "address": addr, "length": size,
                           "hob": "AddMem" if label == "TB520FU_Ramoops" else hob[raw["BuildHob"]], "resource_type": 0 if label == "TB520FU_Ramoops" else raw["ResourceType"],
                           "resource_attribute": 0x703c07 if label == "TB520FU_Ramoops" else raw["ResourceAttribute"], "memory_type": raw["MemoryType"],
                           "cache": "UNCACHED_UNBUFFERED_XN" if label == "TB520FU_Ramoops" else cache[raw["CacheAttributes"]]})
    names = {x["name"]: x for x in output}
    need(names["UEFI_Stack"]["address"] == 0xa760d000 and names["UEFI_Stack"]["length"] == 0x40000,
         "unexpected UEFI stack")
    need(names["Display_Reserved"]["address"] == 0xd5100000, "unexpected framebuffer")
    return output


# Stock hardware drivers keep their original GUID, executable and DEPEX.
# Standard PI/UEFI services use Mu's source implementations.
REPLACE = {
    "DxeCore": "MdeModulePkg/Core/Dxe/DxeMain.inf",
    "RscRtDxe": "MdeModulePkg/Universal/ReportStatusCodeRouter/RuntimeDxe/ReportStatusCodeRouterRuntimeDxe.inf",
    "SCHandlerRtDxe": "MdeModulePkg/Universal/StatusCodeHandler/RuntimeDxe/StatusCodeHandlerRuntimeDxe.inf",
    "ArmCpuDxe": "ArmPkg/Drivers/CpuDxe/CpuDxe.inf",
    "RuntimeDxe": "MdeModulePkg/Core/RuntimeDxe/RuntimeDxe.inf",
    "SecurityStubDxe": "MdeModulePkg/Universal/SecurityStubDxe/SecurityStubDxe.inf",
    "WatchdogTimer": "MdeModulePkg/Universal/WatchdogTimerDxe/WatchdogTimer.inf",
    "CapsuleRuntimeDxe": "MdeModulePkg/Universal/CapsuleRuntimeDxe/CapsuleRuntimeDxe.inf",
    "VariableDxe": "MdeModulePkg/Universal/Variable/RuntimeDxe/VariableRuntimeDxe.inf",
    "EmbeddedMonotonicCounter": "EmbeddedPkg/EmbeddedMonotonicCounter/EmbeddedMonotonicCounter.inf",
    "ResetRuntimeDxe": "MdeModulePkg/Universal/ResetSystemRuntimeDxe/ResetSystemRuntimeDxe.inf",
    "RealTimeClock": "EmbeddedPkg/RealTimeClockRuntimeDxe/RealTimeClockRuntimeDxe.inf",
    "MetronomeDxe": "EmbeddedPkg/MetronomeDxe/MetronomeDxe.inf",
    "HiiDatabase": "MdeModulePkg/Universal/HiiDatabaseDxe/HiiDatabaseDxe.inf",
    "ArmGicDxe": "ArmPkg/Drivers/ArmGicDxe/ArmGicDxe.inf",
    "ArmTimerDxe": "ArmPkg/Drivers/TimerDxe/TimerDxe.inf",
    "DevicePathDxe": "MdeModulePkg/Universal/DevicePathDxe/DevicePathDxe.inf",
    "DiskIoDxe": "MdeModulePkg/Universal/Disk/DiskIoDxe/DiskIoDxe.inf",
    "PartitionDxe": "MdeModulePkg/Universal/Disk/PartitionDxe/PartitionDxe.inf",
    "Fat": "FatPkg/EnhancedFatDxe/Fat.inf",
    "EnglishDxe": "MdeModulePkg/Universal/Disk/UnicodeCollation/EnglishDxe/EnglishDxe.inf",
    "QcomBds": "MdeModulePkg/Universal/BdsDxe/BdsDxe.inf",
    "SimpleTextInOutSerial": "EmbeddedPkg/SimpleTextInOutSerial/SimpleTextInOutSerial.inf",
    "PrintDxe": "MdeModulePkg/Universal/PrintDxe/PrintDxe.inf",
    "ConPlatformDxe": "MdeModulePkg/Universal/Console/ConPlatformDxe/ConPlatformDxe.inf",
    "ConSplitterDxe": "MdeModulePkg/Universal/Console/ConSplitterDxe/ConSplitterDxe.inf",
    "GraphicsConsoleDxe": "MdeModulePkg/Universal/Console/GraphicsConsoleDxe/GraphicsConsoleDxe.inf",
    "UsbBusDxe": "MdeModulePkg/Bus/Usb/UsbBusDxe/UsbBusDxe.inf",
    "UsbKbDxe": "MdeModulePkg/Bus/Usb/UsbKbDxe/UsbKbDxe.inf",
    "UsbMassStorageDxe": "MdeModulePkg/Bus/Usb/UsbMassStorageDxe/UsbMassStorageDxe.inf",
}
SKIP = {"VerifiedBootDxe", "FvSimpleFileSystem", "FvDxe"}
RAW = {"SecParti.cfg", "uefipil.cfg", "QcomChargerCfg.cfg",
       "Panel_lapis_tianma_nt36532_dsc_3k_video.xml", "Panel_lapis_boe_nt36532_dsc_3k_video.xml"}


def prepare(mu, stock, require_pin=True):
    if require_pin:
        head = subprocess.check_output(["git", "-C", str(mu), "rev-parse", "HEAD"], text=True).strip()
        need(head == LOCK["mu_commit"], "Mu source pin mismatch")
        need(not (mu / "Platforms/Lenovo/tb520fuPkg").exists(), "use a fresh Mu checkout")
    data = {}
    for name, sha in LOCK["stock"].items():
        data[name] = (stock / name).read_bytes()
        need(hashlib.sha256(data[name]).hexdigest() == sha, "stock hash mismatch: " + name)
    need(data["boot.img"][:8] == b"ANDROID!" and
         struct.unpack_from("<I", data["boot.img"], 40)[0] == 4, "unexpected stock Android boot header")
    memory = memory_map(data["xbl_config.elf"])
    entries = volumes_from_elf(data["uefi.elf"])
    # Apply only in this dedicated, pinned TB520FU build checkout.
    patch = PORT / "patches/dxe-dispatch-trace.patch"
    if subprocess.run(["git", "-C", str(mu), "apply", "--ignore-whitespace", "--reverse", "--check", str(patch)],
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
        subprocess.run(["git", "-C", str(mu), "apply", "--ignore-whitespace", "--check", str(patch)], check=True)
        subprocess.run(["git", "-C", str(mu), "apply", "--ignore-whitespace", str(patch)], check=True)
    platform = mu / "Platforms/Lenovo/tb520fuPkg"
    platform.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(PORT / "Platforms/Lenovo/tb520fuPkg", platform, dirs_exist_ok=not require_pin)
    shutil.copy2(PORT / "Resources/Configs/tb520fu.toml", mu / "Resources/Configs/tb520fu.toml")
    binaries = mu / "Binaries/tb520fu"
    binaries.mkdir(parents=True, exist_ok=True)
    mapping, order, raw_lines, records = {}, [], [], []
    seen, raw_seen, apriori = set(), set(), []
    for ident, kind, sect in entries:
        if ident == APRIORI:
            for ty, content in sect:
                if ty == 0x19:
                    need(len(content) % 16 == 0, "invalid APRIORI")
                    apriori.extend(guid(content[i:i + 16]) for i in range(0, len(content), 16))
            continue
        name = next((p.decode("utf-16le").rstrip("\0") for t, p in sect if t == 0x15), "")
        need(not name or re.fullmatch(r"[A-Za-z0-9_.-]+", name), "unsafe stock file name")
        pe = next((p for t, p in sect if t == 0x10), None)
        if pe is not None and kind in (5, 7):
            need(name and name not in seen, "duplicate/unnamed stock module")
            seen.add(name)
            if name in SKIP:
                continue
            if name in REPLACE:
                path = REPLACE[name]
            else:
                need(pe[:2] == b"MZ", "expected PE executable: " + name)
                peoff = struct.unpack_from("<I", pe, 0x3c)[0]
                need(pe[peoff:peoff + 4] == b"PE\0\0" and struct.unpack_from("<H", pe, peoff + 4)[0] == 0xaa64,
                     "stock module is not AARCH64: " + name)
                path = f"Binaries/tb520fu/{name}/{name}.inf"
                dest = binaries / name; dest.mkdir(exist_ok=True)
                pe, binary_patch = patch_stock_pe(name, pe)
                (dest / (name + ".efi")).write_bytes(pe)
                depex = next((p for t, p in sect if t == 0x13), None)
                inf = f"[Defines]\n  INF_VERSION = 0x00010005\n  BASE_NAME = {name}\n  FILE_GUID = {ident}\n  MODULE_TYPE = DXE_DRIVER\n  VERSION_STRING = 1.0\n[Packages]\n  MdePkg/MdePkg.dec\n[Binaries.AARCH64]\n  PE32|{name}.efi|*\n"
                if depex is not None:
                    (dest / (name + ".depex")).write_bytes(depex)
                    inf += f"  DXE_DEPEX|{name}.depex|*\n"
                (dest / (name + ".inf")).write_text(inf)
                records.append({"name": name, "guid": ident, "pe_sha256": hashlib.sha256(pe).hexdigest(),
                                "depex_sha256": hashlib.sha256(depex).hexdigest() if depex else None})
                if binary_patch:
                    records[-1]["binary_patch"] = binary_patch
            mapping[ident] = path; order.append(path)
        elif name in RAW:
            content = next(p for t, p in sect if t == 0x19)
            target = binaries / "RawFiles" / name; target.parent.mkdir(exist_ok=True)
            target.write_bytes(content); raw_seen.add(name)
            raw_lines.append(f'  FILE FREEFORM = {ident} {{\n    SECTION UI = "{name}"\n    SECTION RAW = Binaries/tb520fu/RawFiles/{name}\n  }}\n')
            records.append({"name": name, "guid": ident, "raw_sha256": hashlib.sha256(content).hexdigest()})
    need(RAW == raw_seen, "missing TB520FU raw files")
    need(set(REPLACE) <= seen, "missing expected stock service")
    pcd = "MdeModulePkg/Universal/PCD/Dxe/Pcd.inf"
    order.insert(1, pcd)
    forced = [mapping[i] for i in dict.fromkeys(apriori) if i in mapping]
    forced.insert(1, pcd)
    ram = "SiliciumPkg/Drivers/RamManagerDxe/RamManagerDxe.inf"
    smem = next(p for p in forced if "/SmemDxe/" in p)
    forced.insert(forced.index(smem) + 1, ram)
    # IORT is a DT fixup supplied by the Lanai SoC package.
    order.append("QcomPkg/Drivers/IortDtDxe/IortDtDxe.inf")
    inc = platform / "Include"; inc.mkdir(exist_ok=True)
    (inc / "DXE.inc").write_text("".join("  INF " + p + "\n" for p in dict.fromkeys(order)))
    (inc / "APRIORI.inc").write_text("APRIORI DXE {\n" + "".join("  INF " + p + "\n" for p in dict.fromkeys(forced)) + "}\n")
    (inc / "RAW.inc").write_text("".join(raw_lines))
    rows = []
    for m in memory:
        rows.append('  {"%s", 0x%X, 0x%X, %s, 0x%X, 0x%X, 0x%X, %s},' %
                    (m["name"], m["address"], m["length"], m["hob"], m["resource_type"],
                     m["resource_attribute"], m["memory_type"], m["cache"]))
    code = '// SPDX-License-Identifier: BSD-2-Clause-Patent\n// TB520FU stock XBL map, with stock SEC preservation.\n#include <Library/MemoryMapLib.h>\nSTATIC EFI_MEMORY_REGION_DESCRIPTOR gMap[] = {\n' + "\n".join(rows) + '\n};\nVOID GetMemoryMap (OUT EFI_MEMORY_REGION_DESCRIPTOR **Map, OUT UINT8 *Count) {\n  *Map = gMap; *Count = ARRAY_SIZE(gMap);\n}\n'
    (platform / "Library/MemoryMapLib/MemoryMapLib.c").write_text(code)
    cfg = next(p for i, k, ss in entries for t, p in ss if t == 0x19 and b"[ConfigParameters]" in p)
    numeric = {m[1]: int(m[2], 0) for m in re.finditer(rb"(?m)^([A-Za-z0-9_]+)\s*=\s*(0x[0-9a-fA-F]+|[0-9]+)\s*$", cfg)}
    numeric.pop(b"ConfigParameterCount", None)
    numeric.update({b"EnableShell": 1, b"EnableDisplayImageFv": 0, b"EnableDisplayThread": 0,
                    b"EnableMultiThreading": 0, b"EnableMultiCoreFvDecompression": 0})
    rows = [f'  {{"{k.decode()}", 0x{v:X}}},' for k, v in numeric.items()]
    code = '// SPDX-License-Identifier: BSD-2-Clause-Patent\n// TB520FU stock numeric configuration; serial single-core bring-up.\n#include <Library/ConfigurationMapLib.h>\nSTATIC EFI_CONFIGURATION_ENTRY_DESCRIPTOR gMap[] = {\n' + "\n".join(rows) + '\n};\nVOID GetConfigurationMap (OUT EFI_CONFIGURATION_ENTRY_DESCRIPTOR **Map, OUT UINT8 *Count) {\n  *Map = gMap; *Count = ARRAY_SIZE(gMap);\n}\n'
    (platform / "Library/ConfigurationMapLib/ConfigurationMapLib.c").write_text(code)
    report = {"source": LOCK, "stock_modules": records, "memory_regions": memory,
              "standard_source_services": REPLACE, "configuration_count": len(numeric),
              "compile_performed": False, "boot_tested": False}
    (mu / "TB520FU-PREPARED.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"TB520FU UEFI source prepared: {len(records)} stock module/raw entries, {len(memory)} memory regions; no build")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mu", type=Path, required=True, help="fresh checkout at the locked Mu commit")
    parser.add_argument("--stock", type=Path, required=True, help="TB520FU stock image/ directory")
    args = parser.parse_args()
    prepare(args.mu.resolve(), args.stock.resolve())


if __name__ == "__main__":
    main()
