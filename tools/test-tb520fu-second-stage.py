#!/usr/bin/env python3
"""Exercise the actual ARM64 second-stage patches with Unicorn; no device I/O.

Install unicorn==2.1.4 in a local test environment to run this check.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import hashlib
import importlib.util
import struct
import uuid
from pathlib import Path

from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM
from unicorn.arm64_const import (
    UC_ARM64_REG_PC, UC_ARM64_REG_SP, UC_ARM64_REG_LR,
    UC_ARM64_REG_X0, UC_ARM64_REG_X22, UC_ARM64_REG_X29,
)

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("prepare", ROOT / "scripts/prepare-tb520fu-uefi.py")
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--stock", type=Path, required=True)
parser.add_argument("--uefi-prepared", type=Path, required=True)
args = parser.parse_args()
container = (args.stock / "uefi.elf").read_bytes()
assert hashlib.sha256(container).hexdigest() == prepare.LOCK["stock"]["uefi.elf"]
modules = {}
for ident, kind, sections in prepare.volumes_from_elf(container):
    name = next((b.decode("utf-16le").rstrip("\0") for t, b in sections if t == 0x15), "")
    pe = next((b for t, b in sections if t == 0x10), None)
    if pe is not None:
        modules[name] = pe


def machine(pe):
    """Load PE sections at their RVAs rather than assuming raw offsets."""
    uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    uc.mem_map(0, 0x20000)
    header = struct.unpack_from("<I", pe, 60)[0]
    table = header + 24 + struct.unpack_from("<H", pe, header + 20)[0]
    for i in range(struct.unpack_from("<H", pe, header + 6)[0]):
        _, rva, size, offset = struct.unpack_from("<IIII", pe, table + 40 * i + 8)
        uc.mem_write(rva, pe[offset:offset + size])
    uc.mem_map(0x100000, 0x10000)
    uc.reg_write(UC_ARM64_REG_SP, 0x108000)
    uc.reg_write(UC_ARM64_REG_X29, 0x108080)
    uc.reg_write(UC_ARM64_REG_LR, 0x18000)
    return uc


patched = {}
for name, expected_rva, expected_size in (
    ("SPMI", 0x154C, 8), ("TzDxeLA", 0xE5A8, 1),
    ("FeatureEnablerDxe", 0x2370, 8),
):
    original = modules[name]
    result, manifest = prepare.patch_stock_pe(name, original)
    assert int(manifest["rva"], 0) == expected_rva
    assert len(bytes.fromhex(manifest["after"])) == expected_size
    assert len(result) == len(original)
    assert result[:expected_rva] == original[:expected_rva]
    assert result[expected_rva + expected_size:] == original[expected_rva + expected_size:]
    assert result == (args.uefi_prepared / "Binaries/tb520fu" / name / (name + ".efi")).read_bytes()
    for invalid in (b"X" + original[1:], result):
        try:
            prepare.patch_stock_pe(name, invalid)
        except ValueError:
            pass
        else:
            raise AssertionError("mismatched or already patched input was accepted")
    patched[name] = result

# Execute the real wrapper: it must return without touching unconfigured MMIO
# or changing caller buffers. This proves containment, not functional PMIC I/O.
uc = machine(patched["SPMI"])
uc.reg_write(UC_ARM64_REG_X0, 1)
canary = b"caller data stays unchanged"
uc.mem_write(0x100100, canary)
uc.emu_start(0x154C, 0x18000, count=10)
assert uc.reg_read(UC_ARM64_REG_PC) == 0x18000
assert uc.reg_read(UC_ARM64_REG_X0) == 0
assert bytes(uc.mem_read(0x100100, len(canary))) == canary

# Run both the helper and its original caller's error path: unavailable secure
# features must be marked unavailable and never invoke gated feature callbacks.
uc = machine(patched["FeatureEnablerDxe"])
uc.emu_start(0x2370, 0x18000, count=10)
assert uc.reg_read(UC_ARM64_REG_X0) == 0x8000000000000003
uc = machine(patched["FeatureEnablerDxe"])
uc.emu_start(0x1548, 0x1600, count=32)
assert uc.reg_read(UC_ARM64_REG_PC) == 0x1600
assert struct.unpack("<I", uc.mem_read(0x61A0, 4))[0] == 2

# Exercise the stock loader guard with original and patched data. No SMC is
# emulated: the guard must avoid the LoadSecureApps branch in second-stage entry.
for pe, expected_pc in ((modules["TzDxeLA"], 0x2FE0), (patched["TzDxeLA"], 0x2FF0)):
    uc = machine(pe)
    uc.reg_write(UC_ARM64_REG_X22, 0xE000)
    uc.emu_start(0x2FD8, 0x18000, count=2)
    assert uc.reg_read(UC_ARM64_REG_PC) == expected_pc

# Qualcomm label/GPT lookups request these protocols. Stock PartitionDxe must
# be retained exactly, rather than suppressing SPSS errors or modifying storage.
for guid in ("fe2555be-d716-4686-b9d0-79db5921b70d", "6848de61-eb61-4def-9a8e-3817cbeb8f1c"):
    value = uuid.UUID(guid).bytes_le
    assert value in modules["SPSSDxe"] and value in modules["PartitionDxe"]
for name in ("DiskIoDxe", "PartitionDxe"):
    assert name not in prepare.REPLACE
    assert modules[name] == (args.uefi_prepared / "Binaries/tb520fu" / name / (name + ".efi")).read_bytes()
print("Second-stage checks passed: ARM64 SPMI containment, feature error path,")
print("TZ loader guard, exact patch scope/input rejection, stock partition protocols.")
print("Hardware PMIC, secure-world and filesystem operation remain unverified.")
