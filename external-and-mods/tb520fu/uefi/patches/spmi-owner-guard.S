/* SPDX-License-Identifier: BSD-2-Clause-Patent
 * TB520FU stock SPMI.efi trampoline, linked at RVA 0x6f00.
 * Only x9/x10 (caller-saved, not arguments) are used before the stock prologue.
 * x0=context, w1=operation, w3=EE, w4=relative APID.
 * Return values are vendor Spmi_Result, NOT EFI_STATUS.
 * Assemble with aarch64-linux-gnu-as; link -Ttext=0x6f00
 * --defsym=stock_resume=0x3670. Do not use a numeric branch displacement.
 */
.text
.global _start
_start:
    cbz x0, invalid
    ldr x9, [x0, #48]
    cbz x9, invalid
    ldrh w10, [x9]
    cmp w4, w10
    b.hs invalid
    cmp w1, #1
    b.eq allow                 // observer reads can cross write ownership
    cbz w1, owner
    cmp w1, #0x11
    b.ne unsupported
owner:
    ldr x9, [x0, #32]
    cbz x9, invalid
    mov x10, #6
    madd x9, x4, x10, x9
    ldrb w9, [x9, #1]
    and w9, w9, #0x1f         // same node field as stock lookup at 0x35bc
    and w10, w3, #0xff
    cmp w9, w10
    b.ne denied
allow:
    sub sp, sp, #0xe0
    stp x29, x30, [sp, #128]
    b stock_resume            // linker resolves the absolute stock RVA
denied:
    mov w0, #28               // SPMI channel not found for this EE
    b error
unsupported:
    mov w0, #3                // original unsupported operation result
    b error
invalid:
    mov w0, #15               // original invalid transaction result
error:
    ldr x9, [sp]              // ninth argument: bytes-transferred pointer
    cbz x9, done
    str wzr, [x9]
done:
    ret
