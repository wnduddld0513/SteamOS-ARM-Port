#!/usr/bin/env python3
"""Run actual stock/patched SPMI ARM64 instructions against fake arbiter MMIO.

Requires unicorn==2.1.4. No device I/O. This validates transaction behavior,
not access permission or electrical operation on a tablet.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import hashlib
import importlib.util
import json
import struct
import subprocess
import tempfile
from pathlib import Path

from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
from unicorn import arm64_const as regs

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("prepare", ROOT / "scripts/prepare-tb520fu-uefi.py")
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)
ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument("--stock", type=Path, required=True)
ap.add_argument("--uefi-prepared", type=Path, required=True)
args = ap.parse_args()
container = (args.stock / "uefi.elf").read_bytes()
assert hashlib.sha256(container).hexdigest() == prepare.LOCK["stock"]["uefi.elf"]
original = next(b for _, _, ss in prepare.volumes_from_elf(container)
                if any(t == 21 and b.decode("utf-16le").rstrip("\0") == "SPMI" for t, b in ss)
                for t, b in ss if t == 16)
patched, _ = prepare.patch_stock_pe("SPMI", original)
assert patched == (args.uefi_prepared / "Binaries/tb520fu/SPMI/SPMI.efi").read_bytes()
manifest = json.loads((prepare.PORT / "patches/spmi-second-stage.json").read_text())
expected = bytearray(original)
for site in manifest["sites"]:
    offset = int(site["rva"], 0)  # these sites have raw offset == RVA
    before, after = bytes.fromhex(site["before"]), bytes.fromhex(site["after"])
    assert original[offset:offset + len(before)] == before and len(before) == len(after)
    expected[offset:offset + len(after)] = after
assert bytes(expected) == patched
assert patched[0x154c:0x1554] == original[0x154c:0x1554]  # restore real RMW
assert patched[0x7000:] == original[0x7000:]  # preserve TB bus geometry/data/relocations
for invalid in (patched, b"X" + original[1:]):
    try:
        prepare.patch_stock_pe("SPMI", invalid)
    except ValueError:
        pass
    else:
        raise AssertionError("unexpected firmware accepted")

# The committed assembly must reproduce the hash-locked bytes, including its
# backwards branch to the stock prologue; numeric GAS branch operands are relative.
with tempfile.TemporaryDirectory() as td:
    o, elf, binary = [str(Path(td) / name) for name in ("g.o", "g.elf", "g.bin")]
    subprocess.run(["aarch64-linux-gnu-as", "-o", o, str(prepare.PORT / "patches/spmi-owner-guard.S")], check=True)
    subprocess.run(["aarch64-linux-gnu-ld", "-Ttext=0x6f00", "--defsym=stock_resume=0x3670", "--defsym=stock_epilogue=0x3a38", "-o", elf, o], check=True)
    subprocess.run(["aarch64-linux-gnu-objcopy", "-O", "binary", "--only-section=.text", elf, binary], check=True)
    assert Path(binary).read_bytes() == bytes.fromhex(manifest["sites"][1]["after"])

CTX, CFG, NODES, BUF, DONE, STACK = 0x101000, 0x102000, 0x103000, 0x106000, 0x107000, 0x108000
CORE, MMIO_END = 0x0c400000, 0x0c900000


def run(pe, op=1, owner=0, apid=0x4c, count=896, base=0, size=4, status=1, command_first=False, fault_at=None, quarantine=False, initial_status=1):
    uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    uc.mem_map(0, 0x20000)
    header = struct.unpack_from("<I", pe, 60)[0]
    table = header + 24 + struct.unpack_from("<H", pe, header + 20)[0]
    for i in range(struct.unpack_from("<H", pe, header + 6)[0]):
        _, rva, n, raw = struct.unpack_from("<IIII", pe, table + 40 * i + 8)
        uc.mem_write(rva, pe[raw:raw + n])
    uc.mem_map(0x100000, 0x10000)
    uc.mem_map(CORE, MMIO_END - CORE)
    uc.mem_write(CTX, struct.pack("<Q", CORE))
    uc.mem_write(CTX + 32, struct.pack("<Q", NODES))
    uc.mem_write(CTX + 48, struct.pack("<Q", CFG))
    uc.mem_write(CTX + 68, struct.pack("<H", base))
    uc.mem_write(CFG, struct.pack("<H", count))
    uc.mem_write(NODES + apid * 6 + 1, bytes([owner]))
    if quarantine:
        uc.mem_write(0x9f00 + ((base + apid) >> 3), bytes([1 << ((base + apid) & 7)]))
    uc.mem_write(STACK, struct.pack("<Q", DONE))
    uc.mem_write(DONE, struct.pack("<I", 99))
    data = bytes(range(0x31, 0x31 + size))
    uc.mem_write(BUF, data if op != 1 else b"\xcc" * size)
    chan = CORE + (0x40000 + (base + apid) * 0x20 if op == 1 else 0x100000 + (base + apid) * 0x1000)
    uc.mem_write(chan + 8, struct.pack("<I", initial_status))
    uc.mem_write(chan + 0x18, b"\x12\x34\x56\x78\x9a\xbc\xde\xf0")
    accesses, commands = [], []

    def mmio(machine, access, address, n, value, _):
        accesses.append((access, address, n, value))
        if access == 17 and address == chan:  # UC_MEM_WRITE: command register
            commands.append(value)
            machine.mem_write(chan + 8, struct.pack("<I", status))
        if access == 16 and address == chan + 8 and command_first:
            assert commands, "STATUS accessed before CMD"

    def code(machine, address, n, _):
        if address == fault_at:
            # The separately compiled C test checks whether this redirection
            # is accepted. Here execute the actual ARM64 recovery epilogue.
            machine.mem_write(0x9f00 + ((base + apid) >> 3), bytes([1 << ((base + apid) & 7)]))
            machine.reg_write(regs.UC_ARM64_REG_PC, 0x6fd0)
        if address == 0x3c1c:  # vendor delay helper: no real timer or boot services
            machine.reg_write(regs.UC_ARM64_REG_PC, machine.reg_read(regs.UC_ARM64_REG_LR))

    uc.hook_add(UC_HOOK_MEM_READ | UC_HOOK_MEM_WRITE, mmio, begin=CORE, end=MMIO_END - 1)
    uc.hook_add(UC_HOOK_CODE, code)
    for i, value in enumerate((CTX, op, 0, 0, apid, 0x10, BUF, size)):
        uc.reg_write(getattr(regs, "UC_ARM64_REG_X" + str(i)), value)
    saved = {getattr(regs, "UC_ARM64_REG_X" + str(i)): 0x12340000 + i for i in range(19, 30)}
    for reg, value in saved.items():
        uc.reg_write(reg, value)
    uc.reg_write(regs.UC_ARM64_REG_SP, STACK)
    uc.reg_write(regs.UC_ARM64_REG_LR, 0x18000)
    uc.emu_start(0x3668, 0x18000, count=100000)
    assert uc.reg_read(regs.UC_ARM64_REG_PC) == 0x18000, "transfer did not return"
    assert uc.reg_read(regs.UC_ARM64_REG_SP) == STACK, "caller stack not restored"
    assert all(uc.reg_read(reg) == value for reg, value in saved.items()), "callee-saved register changed"
    return uc.reg_read(regs.UC_ARM64_REG_X0), struct.unpack("<I", uc.mem_read(DONE, 4))[0], bytes(uc.mem_read(BUF, size)), accesses, commands


# Reproduce the original hazardous preflight access on otherwise identical MMIO.
try:
    run(original, op=0, owner=4, command_first=True)
except AssertionError as e:
    assert "STATUS accessed before CMD" in str(e)
else:
    raise AssertionError("original transfer no longer reproduces preflight access")

for op in (0, 0x11):
    result, done, data, accesses, commands = run(patched, op=op, owner=4)
    assert result == 28 and done == 0 and not accesses and not commands
for apid, count, base in ((0x4c, 896, 0), (0x277, 896, 0), (127, 128, 896)):
    result, done, data, accesses, commands = run(patched, owner=4, apid=apid, count=count, base=base)
    assert result == 0 and done == 4 and data == b"\x12\x34\x56\x78" and len(commands) == 1
    for op in (0, 0x11):
        result, done, data, accesses, commands = run(patched, op=op, apid=apid, count=count, base=base)
        assert result == 0 and done == 4 and data == b"1234" and len(commands) == 1
        assert any(a == 17 and address % 0x1000 == 0x10 and value == 0x34333231 for a, address, n, value in accesses)
result, done, data, accesses, commands = run(patched, apid=896)
assert result == 15 and done == 0 and not accesses
result, done, data, accesses, commands = run(patched, op=2)
assert result == 3 and done == 0 and not accesses
result, done, data, accesses, commands = run(patched, size=12)
assert result == 0 and done == 12 and data == bytes.fromhex("123456789abcdef012345678") and len(commands) == 2
for status, error in ((3, 5), (5, 6), (9, 7), (0, 8)):
    result, done, data, accesses, commands = run(patched, status=status)
    assert result == error and done == 0 and data == b"\xcc" * 4
result, done, data, accesses, commands = run(patched, initial_status=0)
assert result == 1 and done == 0 and not commands

# v21 failed on WDATA0 at RVA 0x3844. Validate full original stack unwinding,
# zero transferred bytes, and a real denied result rather than a successful stub.
for fault_at, op, size in ((0x37f0, 0, 4), (0x3844, 0, 4), (0x388c, 0, 8),
                           (0x38b8, 0x11, 4), (0x38f4, 0, 4), (0x3914, 0, 4)):
    result, done, data, accesses, commands = run(patched, op=op, size=size, apid=0x27a, fault_at=fault_at)
    assert result == 7 and done == 0 and data == bytes(range(0x31, 0x31 + size))
for op in (0, 0x11):
    result, done, data, accesses, commands = run(patched, op=op, apid=0x27a, quarantine=True)
    assert result == 7 and done == 0 and not accesses
result, done, data, accesses, commands = run(patched, apid=0x27a, quarantine=True)
assert result == 0 and done == 4 and data == bytes.fromhex("12345678")
print("SPMI ARM64 passed: ownership, real reads/writes, both bus geometries, chunking,")
print("abort unwind, write quarantine with observer reads retained, stock ordering, timeout/errors and assembly bytes.")
print("Actual tablet MMIO accessibility, buttons and USB power remain unverified.")
