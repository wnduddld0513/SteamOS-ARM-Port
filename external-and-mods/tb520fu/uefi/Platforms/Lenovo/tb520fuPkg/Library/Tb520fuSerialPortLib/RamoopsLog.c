// SPDX-License-Identifier: BSD-2-Clause-Patent
// TB520FU live DT: 4 MiB ramoops at A2000000, 2 MiB console + 2 MiB pmsg,
// no ECC. Linux persistent_ram_buffer is three little-endian 32-bit words.
#include <Base.h>
#include <Library/ArmLib.h>
#include <Library/BaseLib.h>

#define CONSOLE_BASE  0xA2000000ULL
#define CONSOLE_BYTES 0x200000U
#define RAMOOPS_SIG   0x43474244U

typedef struct {
  volatile UINT32 Sig;
  volatile UINT32 Start;
  volatile UINT32 Size;
  volatile UINT8  Data[CONSOLE_BYTES - 12];
} TB520FU_RAM_CONSOLE;

VOID
Tb520fuRamoopsWrite (IN CONST UINT8 *Buffer, IN UINTN Count)
{
  TB520FU_RAM_CONSOLE *Log = (VOID *)(UINTN)CONSOLE_BASE;
  UINT32 Capacity = CONSOLE_BYTES - 12;
  UINT32 Start;
  UINT32 Size;
  BOOLEAN Interrupts;
  if (Buffer == NULL || Count == 0) {
    return;
  }
  Interrupts = ArmGetInterruptState ();
  ArmDisableInterrupts ();
  Start = Log->Start;
  Size = Log->Size;
  if (Log->Sig != RAMOOPS_SIG || Start > Size || Size > Capacity) {
    Start = 0;
    Size = 0;
    Log->Start = 0;
    Log->Size = 0;
    Log->Sig = RAMOOPS_SIG;
  }
  if (Start == Capacity) {
    Start = 0;
  }
  for (UINTN Index = 0; Index < Count; Index++) {
    Log->Data[Start++] = Buffer[Index];
    if (Start == Capacity) {
      Start = 0;
    }
    if (Size < Capacity) {
      Size++;
    }
  }
  // The memory map keeps the console uncached and reserved, including after
  // RamManagerDxe. Publish data before its indices for the next recovery boot.
  MemoryFence ();
  Log->Size = Size;
  MemoryFence ();
  Log->Start = Start;
  MemoryFence ();
  if (Interrupts) {
    ArmEnableInterrupts ();
  }
}
