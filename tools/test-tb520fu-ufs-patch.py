#!/usr/bin/env python3
"""Verify the TB520FU device-WLUN wakeup patch against local stock firmware."""
# SPDX-License-Identifier: BSD-2-Clause-Patent
import argparse
import hashlib
import importlib.util
from pathlib import Path

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("prepare", root / "scripts/prepare-tb520fu-uefi.py")
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--stock", type=Path, required=True, help="stock image directory")
args = parser.parse_args()
container = (args.stock / "uefi.elf").read_bytes()
assert hashlib.sha256(container).hexdigest() == prepare.LOCK["stock"]["uefi.elf"]
modules = []
for ident, kind, sections in prepare.volumes_from_elf(container):
    name = next((b.decode("utf-16le").rstrip("\0") for t, b in sections if t == 0x15), "")
    if name == "UFSDxe":
        modules.append(next(b for t, b in sections if t == 0x10))
assert len(modules) == 1
stock = modules[0]
patched, manifest = prepare.patch_stock_pe("UFSDxe", stock)
# Only the device-WLUN readiness check changes; the rest of the module is exact.
assert len(stock) == len(patched)
assert patched[:0xA468] == stock[:0xA468]
assert patched[0xA470:] == stock[0xA470:]
assert stock[0xA468:0xA470] == bytes.fromhex("4505009480fdff35")
assert patched[0xA468:0xA470] == bytes.fromhex("210080528f050094")
# Reject a mismatched input and accidental double application.
for invalid in (b"X" + stock[1:], patched):
    try:
        prepare.patch_stock_pe("UFSDxe", invalid)
    except ValueError:
        pass
    else:
        raise AssertionError("incorrect input was accepted")
assert prepare.patch_stock_pe("UnrelatedDxe", stock) == (stock, None)
print("UFS wakeup patch: exact eight-byte scope, guarded input and unchanged unrelated modules verified")
