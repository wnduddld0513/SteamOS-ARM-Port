#!/usr/bin/env python3
"""Compare the supplied Y703 reference with TB520FU stock and a built boot image.

Reads local files only; never distributes firmware or contacts a tablet.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import gzip
import hashlib
import importlib.util
import json
import lzma
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("prepare", ROOT / "scripts/prepare-tb520fu-uefi.py")
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def boot(path):
    data = path.read_bytes()
    assert data[:8] == b"ANDROID!"
    version = struct.unpack_from("<I", data, 40)[0]
    assert version in (3, 4)
    size = struct.unpack_from("<I", data, 8)[0]
    payload = gzip.decompress(data[4096:4096 + size])
    assert len(payload) < 16 * 1024 * 1024
    start = payload.find(b"_FVH", 40) - 40
    assert 0 <= start < 4096
    fv = payload[start:]
    return {"sha256": sha(data), "size": len(data), "header_version": version,
            "kernel_size": size, "shim_size": start, "fd_size": len(fv)}, payload, fv


def unpack(fv):
    entries = list(prepare.files(fv))
    for _, _, ss in list(entries):
        for kind, payload in ss:
            if kind != 2:
                continue
            assert prepare.guid(payload[:16]) == "ee4e5898-3914-4259-9d6e-dc7bd79403cf"
            offset = struct.unpack_from("<H", payload, 16)[0]
            decoded = lzma.decompress(payload[offset - 4:])
            assert len(decoded) < 32 * 1024 * 1024
            nested = [b for t, b in prepare.sections(decoded) if t == 23]
            assert len(nested) == 1
            entries.extend(prepare.files(nested[0]))
    return entries


def modules(entries):
    result = {}
    for guid, kind, ss in entries:
        name = next((b.decode("utf-16le").rstrip("\0") for t, b in ss if t == 21), "")
        pe = next((b for t, b in ss if t == 16), None)
        if pe is not None and name:
            assert name not in result or result[name] == pe, "ambiguous PE name: " + name
            result[name] = pe
    return result


def pe_sections(pe):
    header = struct.unpack_from("<I", pe, 60)[0]
    table = header + 24 + struct.unpack_from("<H", pe, header + 20)[0]
    result = {}
    for i in range(struct.unpack_from("<H", pe, header + 6)[0]):
        off = table + 40 * i
        name = pe[off:off + 8].rstrip(b"\0").decode()
        _, rva, size, raw = struct.unpack_from("<IIII", pe, off + 8)
        result[name] = pe[raw:raw + size]
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reference", type=Path, required=True)
    ap.add_argument("--stock", type=Path, required=True)
    ap.add_argument("--built", type=Path, required=True)
    ap.add_argument("--uefi-prepared", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    ref_info, _, ref_fv = boot(args.reference)
    assert ref_info["sha256"] == "45f923bc3980a8ba6e12ce606c30b4b08c2de48047626648a3d1861c95d2a58f", "different Y703 reference"
    built_info, payload, built_fv = boot(args.built)
    mu = args.uefi_prepared
    assert built_fv == (mu / "Build/tb520fuPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd").read_bytes()
    assert payload[:built_info["shim_size"]] == (mu / "BootShim/BootShim.bin").read_bytes()
    stock = (args.stock / "uefi.elf").read_bytes()
    assert sha(stock) == prepare.LOCK["stock"]["uefi.elf"]
    ref_entries, built_entries = unpack(ref_fv), unpack(built_fv)
    ref, source, built = modules(ref_entries), modules(prepare.volumes_from_elf(stock)), modules(built_entries)
    changes = {}
    for name in sorted(ref.keys() & source.keys()):
        a, b = pe_sections(ref[name])[".text"], pe_sections(source[name])[".text"]
        changes[name] = {"reference_text_sha256": sha(a), "stock_text_sha256": sha(b),
                         "reference_text_size": len(a), "stock_text_size": len(b),
                         "different_bytes": sum(x != y for x, y in zip(a, b)) + abs(len(a) - len(b))}
    assert changes["SPMI"]["different_bytes"] == changes["ButtonsDxe"]["different_bytes"] == 0
    inventory = json.loads((mu / "TB520FU-PREPARED.json").read_text())
    by_guid = {g: ss for g, _, ss in built_entries}
    for item in inventory["stock_modules"]:
        kind, key = (16, "pe_sha256") if "pe_sha256" in item else (25, "raw_sha256")
        content = next(b for t, b in by_guid[item["guid"]] if t == kind)
        assert sha(content) == item[key], "built module/raw mismatch: " + item["name"]
        if item.get("depex_sha256"):
            assert sha(next(b for t, b in by_guid[item["guid"]] if t == 19)) == item["depex_sha256"]
    assert built["SPMI"] == (mu / "Binaries/tb520fu/SPMI/SPMI.efi").read_bytes()
    for name in ("UsbConfigDxe", "UsbBusDxe", "UsbMassStorageDxe"):
        assert built[name] == source[name], "native TB USB driver mismatch: " + name
        for image in (ref[name], built[name]):
            assert b"QcomPkg/" in image, "expected Qualcomm USB driver: " + name
    assert ref["UsbConfigDxe"][0x143b4] == built["UsbConfigDxe"][0x143f4] == 3
    assert ref["UsbConfigDxe"][0x47a8:0x47ac] == built["UsbConfigDxe"][0x47a8:0x47ac] == bytes.fromhex("e1031f2a")
    assert b"BootManagerMenuApp" in b"".join(built.values())
    report = {"reference": ref_info, "built": built_info,
              "reference_ffs_entries": len(ref_entries), "built_ffs_entries": len(built_entries),
              "reference_pe_count": len(ref), "built_pe_count": len(built),
              "reference_only_pe_names": sorted(ref.keys() - built.keys()),
              "built_only_pe_names": sorted(built.keys() - ref.keys()),
              "reference_vs_tb_stock_text": changes,
              "verified_built_stock_entries": len(inventory["stock_modules"]),
              "hardware_boot_tested": False}
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Compared {len(ref)} reference and {len(built)} built PE modules; {len(changes)} shared stock names.")
    print(f"SPMI/Buttons .text identical in Y703 reference and TB stock; all {len(inventory['stock_modules'])} built stock/raw/DEPEX entries verified.")
    print("Native TB USB drivers verified; UsbConfig mode and core-start argument match the working Y703 reference.")
    print("Boot image gzip payload exactly matches the freshly built BootShim and FD.")


if __name__ == "__main__":
    main()
