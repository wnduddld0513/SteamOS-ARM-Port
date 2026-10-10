#!/usr/bin/env python3
"""Host-test the prepared GICv3 handler with an asserted, unowned level IRQ."""
# SPDX-License-Identifier: BSD-2-Clause-Patent
import argparse
from pathlib import Path
import subprocess
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--uefi-prepared", type=Path, required=True)
a = parser.parse_args()
source = (a.uefi_prepared / "Mu_Basecore/ArmPkg/Drivers/ArmGicDxe/GicV3/ArmGicV3Dxe.c").read_text()
start = source.index("GicV3IrqInterruptHandler (")
end = source.index("\nEFI_STATUS", start)
handler = "static void " + source[start:end]
prefix = r"""
#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#define IN
#define DEBUG_ERROR 1
#define DEBUG(x) mock_debug x
#define UINT32 uint32_t
#define UINTN uintptr_t
#define EFI_EXCEPTION_TYPE int
#define EFI_SYSTEM_CONTEXT void *
typedef void (*HARDWARE_INTERRUPT_HANDLER)(UINTN, EFI_SYSTEM_CONTEXT);
static int gHardwareInterruptV3Protocol;
static int mode, step, callbacks;
static HARDWARE_INTERRUPT_HANDLER slot;
static UINTN ArmGicV3AcknowledgeInterrupt(void) { return mode == 2 ? 1023 : 0x105; }
static int GicCommonSourceIsSpecialInterrupt(UINTN irq) { return irq == 1023; }
static HARDWARE_INTERRUPT_HANDLER *GicV3GetHandlerAddress(UINTN irq) {
  assert(irq == 0x105); return mode == 3 ? NULL : &slot;
}
static void GicV3DisableInterruptSource(void *p, UINTN irq) {
  assert(p == &gHardwareInterruptV3Protocol && irq == 0x105 && step == 0); step = 1;
}
static void GicV3EndOfInterrupt(void *p, UINTN irq) {
  assert(p == &gHardwareInterruptV3Protocol && irq == 0x105 && step == 1); step = 2;
}
static void mock_debug(int level, const char *format, ...) {
  (void)level; (void)format;
  if (mode == 0) { assert(step == 2); step = 3; }
}
static void owned_handler(UINTN irq, EFI_SYSTEM_CONTEXT ctx) {
  assert(irq == 0x105 && ctx == (void *)1 && step == 0); callbacks++;
}
"""
suffix = r"""
int main(void) {
  mode = 0; slot = NULL; GicV3IrqInterruptHandler(0, NULL); assert(step == 3);
  mode = 1; step = 0; slot = owned_handler;
  GicV3IrqInterruptHandler(0, (void *)1); assert(step == 0 && callbacks == 1);
  mode = 2; GicV3IrqInterruptHandler(0, NULL); assert(step == 0);
  mode = 3; GicV3IrqInterruptHandler(0, NULL); assert(step == 0);
  return 0;
}
"""
with tempfile.TemporaryDirectory() as temp:
    c = Path(temp) / "handler.c"; exe = Path(temp) / "handler"
    c.write_text(prefix + handler + suffix)
    subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Wno-unused-parameter", str(c), "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
print("GIC handler: mask and EOI precede logging; owned, special and invalid IRQ paths preserved")
