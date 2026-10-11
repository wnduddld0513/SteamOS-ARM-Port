#!/usr/bin/env python3
"""Compile and execute the actual exception fixup against positive/negative contexts.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import re
import struct
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORT = ROOT / "external-and-mods/tb520fu/uefi"
ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument("--uefi-prepared", type=Path, required=True)
args = ap.parse_args()
header = PORT / "patches/spmi-abort-recovery.h"
prepared = args.uefi_prepared / "Mu_Basecore/UefiCpuPkg/Library/CpuExceptionHandlerLib/AArch64"
assert header.read_bytes() == (prepared / "Tb520fuSpmiRecovery.h").read_bytes()
source = (prepared / "CpuExceptionHandlerLib.c").read_text()
assert source.index("if (Tb520fuRecoverSpmiAbort") < source.index("if ((UINTN)ExceptionType <= mMaxExceptionNumber)")
pe = (args.uefi_prepared / "Binaries/tb520fu/SPMI/SPMI.efi").read_bytes()
for rva, instruction in re.findall(r"case (0x[0-9A-F]+): Instruction = (0x[0-9A-F]+);", header.read_text()):
    assert struct.unpack_from("<I", pe, int(rva, 0))[0] == int(instruction, 0)
for rva, instruction in re.findall(r"Base \+ (0x[0-9A-F]+)\) != (0x[0-9A-F]+)", header.read_text()):
    assert struct.unpack_from("<I", pe, int(rva, 0))[0] == int(instruction, 0)
assert pe[0x9f00:0x9f80] == bytes(128)

harness = r'''
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <stdlib.h>
#include <assert.h>
#define STATIC static
#define IN
#define CONST const
#define TRUE 1
#define FALSE 0
#define DEBUG(x) ((void)0)
typedef uint64_t UINT64;
typedef uintptr_t UINTN;
typedef uint32_t UINT32;
typedef uint8_t UINT8;
typedef char CHAR8;
typedef int BOOLEAN;
typedef int EFI_EXCEPTION_TYPE;
// Host representation of the fields used by the exact recovery function.
// ARM64 register/stack restoration is tested separately in Unicorn.
typedef struct {
 UINT64 ESR,FAR,ELR,SP,FP,X3,X4,X9,X10,X12,X13,X15,X25;
} EFI_SYSTEM_CONTEXT_AARCH64;
typedef union { EFI_SYSTEM_CONTEXT_AARCH64 *SystemContextAArch64; } EFI_SYSTEM_CONTEXT;
static UINT8 Image[0xb000];
static CHAR8 *ImageName="SPMI.dll";
static UINTN ImageHeaders=0x1000;
static CHAR8 *GetImageName(UINTN a,UINTN *b,UINTN *h) {
 *b=(UINTN)Image;*h=ImageHeaders;return ImageName;
}
static CHAR8 *BaseName(CHAR8 *s) { return s; }
#define AsciiStrCmp strcmp
#include "RECOVERY_HEADER"
static void word(size_t offset,UINT32 value) { memcpy(Image+offset,&value,4); }
int main(void) {
 size_t rvas[]={0x37f0,0x3844,0x388c,0x38b8,0x38f4,0x3914};
 UINT32 ops[]={0xb8646869,0xb82d698b,0xb8296948,0xb82469e8,0xb82969e8,0xb9400328};
 word(0x6fd0,0xf94013f0);word(0x6fd4,0xb900021f);
 word(0x6fd8,0x528000e0);word(0x6fdc,0x17fff297);
 for(size_t i=0;i<6;i++) {
  EFI_SYSTEM_CONTEXT_AARCH64 c={0},original;
  EFI_SYSTEM_CONTEXT u={&c};
  c.ESR=0x96000010;c.FAR=0xc77a010;
  c.ELR=(UINTN)Image+rvas[i];c.SP=0xa764b680;c.FP=c.SP+128;
  // Independently populate each reviewed addressing mode.
  switch(i) {
   case 0:c.X3=0xc500010;c.X4=0x27a000;break;
   case 1:c.X12=0xc500010;c.X13=0x27a000;break;
   case 2:c.X10=0xc500010;c.X9=0x27a000;break;
   case 3:c.X15=0xc500010;c.X4=0x27a000;break;
   case 4:c.X15=0xc500010;c.X9=0x27a000;break;
   case 5:c.X25=c.FAR;break;
  }
  word(rvas[i],ops[i]);original=c;
  Image[0x9f00+(0x27a>>3)]=0;
  assert(Tb520fuRecoverSpmiAbort(0,u));
  assert(c.ELR==(UINTN)Image+0x6fd0);
  c.ELR=original.ELR;assert(memcmp(&c,&original,sizeof c)==0);
  assert(Image[0x9f00+(0x27a>>3)]==(1<<(0x27a&7)));
  // Unrelated exceptions, bad operands/frame/name/code must remain fatal.
  assert(!Tb520fuRecoverSpmiAbort(1,u));
  c.ESR=0x9600000f;assert(!Tb520fuRecoverSpmiAbort(0,u));c=original;
  c.ESR|=0x400;assert(!Tb520fuRecoverSpmiAbort(0,u));c=original;
  c.ESR|=0x80;assert(!Tb520fuRecoverSpmiAbort(0,u));c=original;
  c.FAR+=4;assert(!Tb520fuRecoverSpmiAbort(0,u));c=original;
  c.FAR=0xc440008;assert(!Tb520fuRecoverSpmiAbort(0,u));c=original;
  c.FP+=16;assert(!Tb520fuRecoverSpmiAbort(0,u));c=original;
  c.SP=0xa764d000;c.FP=c.SP+128;assert(!Tb520fuRecoverSpmiAbort(0,u));c=original;
  c.ELR=(UINTN)Image+0x4000;assert(!Tb520fuRecoverSpmiAbort(0,u));c=original;
  ImageName="ClockDxe.dll";assert(!Tb520fuRecoverSpmiAbort(0,u));ImageName="SPMI.dll";
  ImageName=NULL;assert(!Tb520fuRecoverSpmiAbort(0,u));ImageName="SPMI.dll";
  ImageHeaders=0;assert(!Tb520fuRecoverSpmiAbort(0,u));ImageHeaders=0x1000;
  word(rvas[i],0);assert(!Tb520fuRecoverSpmiAbort(0,u));word(rvas[i],ops[i]);
  word(0x6fdc,0);assert(!Tb520fuRecoverSpmiAbort(0,u));word(0x6fdc,0x17fff297);
 }
 return 0;
}
'''.replace("RECOVERY_HEADER", str(header))
with tempfile.TemporaryDirectory() as td:
    c = Path(td) / "test.c"
    exe = Path(td) / "test"
    c.write_text(harness)
    subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Wno-unused-parameter", "-o", str(exe), str(c)], check=True)
    subprocess.run([str(exe)], check=True)
print("Actual recovery C passed: all six MMIO sites, code/FAR/frame checks, quarantine and unrelated-fault rejection.")
