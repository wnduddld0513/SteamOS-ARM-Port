#!/usr/bin/env python3
"""Exercise the actual firmware ring writer in host memory, without device access."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "external-and-mods/tb520fu/uefi/Platforms/Lenovo/tb520fuPkg/Library/Tb520fuSerialPortLib/RamoopsLog.c"

BASE = """
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
typedef uint8_t UINT8;
typedef uint32_t UINT32;
typedef uint64_t UINT64;
typedef uintptr_t UINTN;
typedef bool BOOLEAN;
#define VOID void
#define IN
#define CONST const
"""
HARNESS = r"""
#include <assert.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
static BOOLEAN InterruptState = true;
BOOLEAN ArmGetInterruptState(void) { return InterruptState; }
void ArmDisableInterrupts(void) { InterruptState = false; }
void ArmEnableInterrupts(void) { InterruptState = true; }
void MemoryFence(void) { __sync_synchronize(); }
int main(void) {
  unsigned char *mem = mmap((void *)0xA2000000, 0x400000,
      PROT_READ|PROT_WRITE, MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE, -1, 0);
  assert(mem != MAP_FAILED);
  memset(mem, 0xA5, 0x400000);
  UINT32 *header = (UINT32 *)mem;
  UINT8 *data = mem + 12;
  UINT32 capacity = 0x200000 - 12;
  Tb520fuRamoopsWrite((UINT8 *)"ENTER Clock\n", 12);
  assert(InterruptState);
  assert(header[0] == 0x43474244 && header[1] == 12 && header[2] == 12);
  assert(memcmp(data, "ENTER Clock\n", 12) == 0);
  InterruptState = false;
  Tb520fuRamoopsWrite((UINT8 *)"EXIT Clock\n", 11);
  assert(!InterruptState && header[1] == 23 && header[2] == 23);
  UINT8 *input = malloc(capacity + 17);
  assert(input != NULL);
  for (UINTN i = 0; i < capacity + 17; i++) input[i] = 'A' + i % 26;
  Tb520fuRamoopsWrite(input, capacity + 17);
  assert(header[2] == capacity);
  // Linux persistent_ram_save_old reads data[start:size], then data[0:start].
  for (UINTN i = 0; i < capacity; i++) {
    assert(data[(header[1] + i) % capacity] == input[i + 17]);
  }
  for (UINTN i = 0x200000; i < 0x400000; i++) assert(mem[i] == 0xA5);
  UINT32 old_start = header[1], old_size = header[2];
  Tb520fuRamoopsWrite(NULL, 42);
  Tb520fuRamoopsWrite(input, 0);
  assert(header[1] == old_start && header[2] == old_size);
  header[1] = capacity + 1;
  Tb520fuRamoopsWrite((UINT8 *)"OK", 2);
  assert(header[1] == 2 && header[2] == 2 && data[0] == 'O' && data[1] == 'K');
  // Observed recovery rejection: both values fit, but start exceeds size.
  header[1] = 485717; header[2] = 223573;
  Tb520fuRamoopsWrite((UINT8 *)"OK", 2);
  assert(header[1] == 2 && header[2] == 2);
  free(input);
  return 0;
}
"""

def main():
    with tempfile.TemporaryDirectory(prefix="tb520fu-ramoops-test-") as td:
        p = Path(td)
        (p / "Library").mkdir()
        (p / "Base.h").write_text(BASE)
        (p / "Library/ArmLib.h").write_text("BOOLEAN ArmGetInterruptState(void); void ArmDisableInterrupts(void); void ArmEnableInterrupts(void);\n")
        (p / "Library/BaseLib.h").write_text("void MemoryFence(void);\n")
        (p / "test.c").write_text('#include "' + str(SOURCE) + '"\n' + HARNESS)
        subprocess.run(["cc", "-std=gnu11", "-Wall", "-Wextra", "-Werror", "-I", str(p), str(p / "test.c"), "-o", str(p / "test")], check=True)
        subprocess.run([str(p / "test")], check=True)
    print("Firmware ramoops writer: append, Linux readback order, wrap, invalid headers, interrupt state and pmsg isolation passed")

if __name__ == "__main__":
    main()
