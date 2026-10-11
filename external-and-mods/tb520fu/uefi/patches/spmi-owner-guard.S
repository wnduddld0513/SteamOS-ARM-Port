/* SPDX-License-Identifier: BSD-2-Clause-Patent
 * TB520FU stock SPMI.efi trampoline, linked at RVA 0x6f00.
 * Only x9/x10/x11 (caller-saved, not arguments) are used before the prologue.
 * x0=context, w1=operation, w3=EE, w4=relative APID.
 * Return values are vendor Spmi_Result, NOT EFI_STATUS.
 * Assemble with aarch64-linux-gnu-as; link -Ttext=0x6f00
 * --defsym=stock_resume=0x3670 --defsym=stock_epilogue=0x3a38.
 * Do not use a numeric branch displacement.
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
    // Do not retry a write channel whose MMIO raised an external abort.
    // The CPU exception fixup records it in unused writable data at RVA 9f00.
    ldrh w10, [x0, #68]
    add w10, w10, w4
    cmp w10, #1024
    b.hs invalid
    and w11, w10, #7
    lsr w10, w10, #3
    adrp x9, _start
    add x9, x9, #3, lsl #12
    add x9, x9, #0xf00
    ldrb w10, [x9, x10]
    lsr w10, w10, w11
    tbnz w10, #0, bus_denied
allow:
    sub sp, sp, #0xe0
    stp x29, x30, [sp, #128]
    b stock_resume            // linker resolves the absolute stock RVA
denied:
    mov w0, #28               // SPMI channel not found for this EE
    b error
bus_denied:
    mov w0, #7                // stock raw-transfer bus-denied result
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

    .org 0xd0                 // recovery entry is fixed at RVA 0x6fd0
fault_resume:
    ldr x16, [sp, #32]        // stock raw transfer's saved byte-count pointer
    str wzr, [x16]
    mov w0, #7
    b stock_epilogue          // restore caller registers and the original stack
