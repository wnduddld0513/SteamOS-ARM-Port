// SPDX-License-Identifier: BSD-2-Clause-Patent
// Included after BaseName() in the private TB520FU AArch64 exception library.
// This is a transfer fixup, not a general-purpose exception suppression path.
STATIC
BOOLEAN
Tb520fuRecoverSpmiAbort (
  IN EFI_EXCEPTION_TYPE ExceptionType,
  IN EFI_SYSTEM_CONTEXT SystemContext
  )
{
  EFI_SYSTEM_CONTEXT_AARCH64 *C;
  UINTN Base, Headers, Rva, Apid;
  UINT64 Address;
  UINT32 Instruction;
  CHAR8 *Name;
  UINT8 *Quarantine;

  C = SystemContext.SystemContextAArch64;
  // Same-EL synchronous external Data Abort, valid FAR, no page-table walk.
  if ((ExceptionType != 0) || ((C->ESR >> 26) != 0x25) ||
      ((C->ESR & 0x4BF) != 0x10) ||
      (C->FAR < 0x0C500000) || (C->FAR >= 0x0C900000) ||
      (C->SP < 0xA760D000) || (C->SP > 0xA764CF20) ||
      ((C->SP & 15) != 0) || (C->FP != C->SP + 128)) {
    return FALSE;
  }

  Base = 0;
  Headers = 0;
  Name = GetImageName (C->ELR, &Base, &Headers);
  if ((Name == NULL) || (AsciiStrCmp (BaseName (Name), "SPMI.dll") != 0) ||
      (Headers != 0x1000) || (C->ELR < Base) || (C->ELR - Base >= 0x7000)) {
    return FALSE;
  }

  Rva = (UINTN)(C->ELR - Base);
  // Each entry is a reviewed instruction in the pinned raw-transfer frame.
  // Compute the effective address independently from its saved operands.
  switch (Rva) {
    case 0x37F0: Instruction = 0xB8646869; Address = C->X3 + C->X4; break;
    case 0x3844: Instruction = 0xB82D698B; Address = C->X12 + C->X13; break;
    case 0x388C: Instruction = 0xB8296948; Address = C->X10 + C->X9; break;
    case 0x38B8: Instruction = 0xB82469E8; Address = C->X15 + C->X4; break;
    case 0x38F4: Instruction = 0xB82969E8; Address = C->X15 + C->X9; break;
    case 0x3914: Instruction = 0xB9400328; Address = C->X25; break;
    default: return FALSE;
  }

  // Validate the actual instruction and this build's recovery epilogue.
  if ((Address != C->FAR) ||
      (*(CONST UINT32 *)(UINTN)C->ELR != Instruction) ||
      (*(CONST UINT32 *)(Base + 0x6FD0) != 0xF94013F0) ||
      (*(CONST UINT32 *)(Base + 0x6FD4) != 0xB900021F) ||
      (*(CONST UINT32 *)(Base + 0x6FD8) != 0x528000E0) ||
      (*(CONST UINT32 *)(Base + 0x6FDC) != 0x17FFF297)) {
    return FALSE;
  }

  Apid = (UINTN)((C->FAR - 0x0C500000) >> 12);
  Quarantine = (UINT8 *)(Base + 0x9F00);
  Quarantine[Apid >> 3] |= (UINT8)(1U << (Apid & 7));
  // The assembly clears transferred bytes and runs the stock register/stack
  // epilogue with vendor result 7 (same result as channel STATUS.DENIED).
  C->ELR = Base + 0x6FD0;
  DEBUG ((DEBUG_WARN, "TB520FU SPMI write channel 0x%x inaccessible at RVA 0x%x; returning denied\n", Apid, Rva));
  return TRUE;
}
