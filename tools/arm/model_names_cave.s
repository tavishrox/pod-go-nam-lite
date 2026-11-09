@ NAM Model knob: "slot name" instead of a number. Entered from the float value formatter's
@ display-type table (dynamicList, 12) inside 0x28cc8f20's frame:
@   s16 = the knob's value (0..1), r5 = out text, r6 = its size. Exit: 0x28cc8f6c (return 0).
.syntax unified
.thumb





.global cave
cave:
    cmp     r6, #12
    blo     fallback
    vldr    s15, k100
    vmul.f32 s15, s16, s15
    vmov.f32 s14, #0.5
    vadd.f32 s15, s15, s14
    vcvt.s32.f32 s15, s15
    vmov    r4, s15
    adds    r4, #1                  @ the slot, as the kernel decodes it: TRUNC(100 v + 0.5) + 1
    cmp     r4, #1
    blt     fallback
    cmp     r4, #128
    bgt     fallback
    mov     r0, r4
    mov     r1, r5
    bl      ITOA                    @ r0 = digits written
    adds    r7, r5, r0
    movs    r2, #0x20
    strb    r2, [r7], #1            @ "4 "
    subs    r8, r6, r0
    sub     r8, r8, #2              @ room left for the name, less its NUL
    subs    r0, r4, #1
    rsb     r0, r0, r0, lsl #4      @ (slot - 1) * 15
    ldr     r1, knames
    add.w   r1, r1, r0, lsl #3      @ the IR table's record (0x78 bytes): its name at +8 (64 chars)
    mov     r0, r7
    mov     r2, r8
    bl      STRNCPY
    adds    r3, r5, r6
    movs    r2, #0
    strb    r2, [r3, #-1]           @ always terminated
    b.w     EXIT
fallback:
    b.w     DEFAULT
    .align 2
k100: .float 100.0
knames: .word 0x282c6f9c     @ 0x282c6f94 + 8, as 0x28cbdf30 (the app's name getter) has it
EXIT: nop
DEFAULT: nop
ITOA: nop
STRNCPY: nop
