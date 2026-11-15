@ Six snapshots on the POD Go 2.50, steps (a) and (b): snapshots 5 and 6 share slot 4 (docs/research/SNAPSHOTS_6.md).
@
@ The stock code keeps four 0x28c-byte snapshot records in the snapshot manager (0x281247d4). Here
@ slot 4 (index 3) is a window: `holder` says which of snapshots 4, 5, 6 (index 3, 4, 5) it holds, and
@ the other two wait in `store`. Selecting index 3..5 swaps the wanted one into slot 4, then lets the stock
@ select apply it. A new preset (the manager's reset) puts slot 4 back to snapshot 4 and empties the store.
@
@ Hooks (podgo/snapshots6.py writes them):
@   0x28cb88a4 select(mgr, idx): its push.w becomes b.w sel_hook
@   0x28cb7878 reset(mgr):       its push.w becomes b.w reset_hook
@   0x28cb6496 MIDI CC69:        cmp r4,#3 -> cmp r4,#5 (values 4 and 5 reach select)
@   0x28cb916c / 0x28cb984c snapshot section write / read: b.w ser_hook / des_hook (step (b), below)
@   0x28c9604a / 0x28c96176 bl to the preset writers: bl st_feac / st_fa6c (mark a save to the store)
@ Not done yet: the display and footswitches know four snapshots.

        .syntax unified
        .thumb

        .equ SELECT_BODY, 0x28cb88a8
        .equ RESET_BODY,  0x28cb787c
        .equ LOCK,        0x28c7cab8
        .equ UNLOCK,      0x28c7cacc
        .equ MEMCPY,      0x28cd9f70
        .equ RECSZ,       0x28c
        .equ SLOT4,       0x7b0          @ 0xc + 3 * RECSZ
        .equ SLOT3,       0x524          @ 0xc + 2 * RECSZ
        .equ VALID,       0x277          @ in a record (stock: mgr + idx*RECSZ + 0x283)
        .equ NAME,        0x27e          @ in a record, 11 bytes
        .equ CUR,         0xa4b
        .equ PREV,        0xa4c
        .equ LOCKED,      0xcdd

        .text
        .global sel_hook, reset_hook, orig_select
        .type sel_hook, %function
        .type reset_hook, %function
        .type orig_select, %function

@ r0 = manager, r1 = index; entered by b.w from the stock select, lr = its caller
        .thumb_func
sel_hook:
        push    {r0-r3, ip, lr}         @ DEBUG: dbg[64..] at entry, caller at dbg[120]
        ldr     r2, =dbg
        str     lr, [r2, #120]
        strb    r1, [r2, #124]
        mov     r1, r0
        movs    r0, #64
        bl      probe
        pop     {r0-r3, ip, lr}
        cmp     r1, #3
        blo     orig_select
        cmp     r1, #5
        bhi     orig_select
        ldrb.w  r2, [r0, #LOCKED]
        cbz     r2, 1f
        b       orig_select
1:      push    {r4-r10, lr}
        mov     r4, r0                  @ manager
        mov     r5, r1                  @ wanted: 3..5
        ldr     r6, =state
        ldrb    r3, [r6]                @ holder (0 before the first reset: slot 4 holds snapshot 4)
        cmp     r3, #3
        it      lo
        movlo   r3, #3
        strb    r3, [r6]
        cmp     r3, r5
        beq     same

        adds    r0, r4, #4
        ldr     ip, =LOCK + 1
        blx     ip
        addw    r7, r4, #SLOT4
        @ slot 4 -> store[holder - 3]
        ldrb    r3, [r6]
        subs    r3, #3
        adds    r2, r6, r3
        movs    r1, #1
        strb    r1, [r2, #1]            @ valid[holder - 3]
        movw    r2, #RECSZ
        ldr     r0, =store
        mla     r0, r2, r3, r0
        mov     r1, r7
        ldr     ip, =MEMCPY + 1
        blx     ip
        @ store[wanted - 3] -> slot 4, or a new snapshot: a copy of the current one, named
        subs    r3, r5, #3
        adds    r2, r6, r3
        ldrb    r1, [r2, #1]
        cbz     r1, fresh
        movw    r2, #RECSZ
        ldr     r1, =store
        mla     r1, r2, r3, r1
        mov     r0, r7
        ldr     ip, =MEMCPY + 1
        blx     ip
        b       loaded
fresh:  movs    r1, #1
        strb    r1, [r2, #1]
        ldrb.w  r1, [r4, #CUR]
        cmp     r1, #3
        beq     2f                      @ on slot 4 already: it holds the current one
        movw    r2, #RECSZ
        mla     r1, r2, r1, r4
        adds    r1, #0xc
        mov     r0, r7
        ldr     ip, =MEMCPY + 1
        blx     ip
2:      movs    r1, #1
        strb.w  r1, [r7, #VALID]
        ldr     r1, =names
        subs    r3, r5, #4              @ 0 for snapshot 5, 1 for 6
        movs    r2, #12
        mla     r1, r2, r3, r1
        addw    r0, r7, #NAME
        movs    r2, #11
        ldr     ip, =MEMCPY + 1
        blx     ip
loaded: ldrb    r9, [r6]                @ the snapshot slot 4 held: store index
        cmp     r9, #3
        it      lo
        movlo   r9, #3
        sub     r9, r9, #3
        strb    r5, [r6]                @ holder = wanted
        @ The stock select only applies what differs between the record it leaves (CUR) and the new
        @ one. Leaving slot 4 for slot 4, lend it slot 3 (index 2) holding the snapshot we leave, so it
        @ compares the right two; afterwards that copy (with anything select wrote back into it) goes to
        @ the store and slot 3 is put back.
        movs    r8, #0
        ldrb.w  r3, [r4, #CUR]
        cmp     r3, #3
        bne     3f
        addw    r10, r4, #SLOT3
        ldr     r0, =tmp
        mov     r1, r10
        movw    r2, #RECSZ
        ldr     ip, =MEMCPY + 1
        blx     ip
        ldr     r1, =store
        movw    r2, #RECSZ
        mla     r1, r2, r9, r1
        mov     r0, r10
        ldr     ip, =MEMCPY + 1
        blx     ip
        movs    r3, #2
        strb.w  r3, [r4, #CUR]
        movs    r8, #1
3:      movs    r0, #72             @ DEBUG: just before the stock select
        mov     r1, r4
        bl      probe
        adds    r0, r4, #4
        ldr     ip, =UNLOCK + 1
        blx     ip
        mov     r0, r4
        movs    r1, #3
        bl      orig_select
        movs    r0, #80             @ DEBUG: just after it
        mov     r1, r4
        bl      probe
        cmp     r8, #0
        beq     4f
        adds    r0, r4, #4
        ldr     ip, =LOCK + 1
        blx     ip
        ldr     r0, =store
        movw    r2, #RECSZ
        mla     r0, r2, r9, r0
        mov     r1, r10
        ldr     ip, =MEMCPY + 1
        blx     ip
        mov     r0, r10
        ldr     r1, =tmp
        movw    r2, #RECSZ
        ldr     ip, =MEMCPY + 1
        blx     ip
        movs    r3, #3
        strb.w  r3, [r4, #PREV]         @ the snapshot we came from was slot 4
        adds    r0, r4, #4
        ldr     ip, =UNLOCK + 1
        blx     ip
4:      movs    r0, #88             @ DEBUG: on the way out
        mov     r1, r4
        bl      probe
        pop     {r4-r10, pc}

@ Leaving six mode: slot 4 is the four-snapshot view's "4", so snapshot 4's record goes back into it and the
@ one it held (5 or 6) to the store, without a select. Not when slot 4 is the snapshot playing (its sound must
@ not change): then the view's 4 shows it until another snapshot is picked, and picking 4 swaps snapshot 4 in
@ (sel_hook) as in six mode.
        .thumb_func
        .type give_back, %function
give_back:
        push    {r4-r7, lr}
        ldr     ip, =GET_MGR + 1
        blx     ip
        mov     r4, r0
        ldr     r6, =state
        ldrb    r5, [r6]                @ holder
        cmp     r5, #3
        bls     9f                      @ snapshot 4 is there
        ldrb.w  r3, [r4, #LOCKED]
        cbnz    r3, 9f
        ldrb.w  r3, [r4, #CUR]
        cmp     r3, #3
        beq     9f                      @ slot 4 is playing: leave it
        ldrb    r3, [r6, #1]            @ snapshot 4 kept in the store?
        cbz     r3, 9f
        adds    r0, r4, #4
        ldr     ip, =LOCK + 1
        blx     ip
        addw    r7, r4, #SLOT4
        subs    r3, r5, #3
        adds    r2, r6, r3
        movs    r1, #1
        strb    r1, [r2, #1]            @ valid[holder - 3]
        movw    r2, #RECSZ
        ldr     r0, =store
        mla     r0, r2, r3, r0
        mov     r1, r7
        ldr     ip, =MEMCPY + 1
        blx     ip                      @ slot 4 -> store[holder - 3]
        mov     r0, r7
        ldr     r1, =store
        movw    r2, #RECSZ
        ldr     ip, =MEMCPY + 1
        blx     ip                      @ store[0] (snapshot 4) -> slot 4
        movs    r3, #3
        strb    r3, [r6]                @ holder: snapshot 4
        adds    r0, r4, #4
        ldr     ip, =UNLOCK + 1
        blx     ip
9:      pop     {r4-r7, pc}

@ DEBUG probe: dbg[r0..r0+7] = byte PROBE_B of records 1-4, store 0-2, then CUR. r1 = manager. Clobbers r0-r3, ip.
        .equ PROBE_B, 6
        .thumb_func
probe:  ldr     r2, =dbg
        add     r0, r2
        movs    r2, #0
1:      movw    r3, #RECSZ
        mla     r3, r3, r2, r1
        ldrb    ip, [r3, #0xc + PROBE_B]
        strb    ip, [r0, r2]
        adds    r2, #1
        cmp     r2, #4
        blo     1b
        movs    r2, #0
2:      ldr     r3, =store
        movw    ip, #RECSZ
        mla     r3, ip, r2, r3
        ldrb    ip, [r3, #PROBE_B]
        adds    r3, r0, r2
        strb    ip, [r3, #4]
        adds    r2, #1
        cmp     r2, #3
        blo     2b
        ldrb.w  ip, [r1, #CUR]
        strb    ip, [r0, #7]
        bx      lr

same:   mov     r0, r4
        movs    r1, #3
        pop     {r4-r10, lr}
        .thumb_func
orig_select:
        push.w  {r4-r11, lr}            @ the stock first instruction
        ldr.w   pc, =SELECT_BODY + 1

@ r0 = manager; entered by b.w from the stock reset (a tail call: lr is its caller's)
        .thumb_func
reset_hook:
        ldr     r2, =state
        movs    r3, #3
        strb    r3, [r2]
        movs    r3, #0
        strb    r3, [r2, #1]
        strb    r3, [r2, #2]
        strb    r3, [r2, #3]
        push.w  {r4-r9, lr}             @ the stock first instruction
        ldr.w   pc, =RESET_BODY + 1

        .ltorg

@ ---- step (b): snapshots 5 and 6 saved with the preset -------------------------------------------
@ Only when a preset is written to the unit's own store (the two bl's in 0x28c95fb4 / 0x28c960e0 go
@ through st_feac / st_fa6c, which set `storing`), the snapshot section becomes
@   (0a) 87 0e c5 LL LL  holder mask 00 00  [records] 0a 86 06 ...
@ a valid MessagePack map(7) {14: bin, 6: ..}: the bin ends with a copy of the key byte 0a and the stock
@ serializer's own map(6) header 86. The loaders hand the reader the section from its key byte 0a on, so
@ the stock reader is given the bytes from our 0a: `0a 86 06 ..`, and never sees key 14.
@ mask: bit i = store[i] (snapshot 4+i) saved, never the holder's (it is in slot 4 itself).
@ Nothing extra is written when there is nothing in the store: those presets stay byte-for-byte stock.
@ POD Go Edit's reads (0x28c8b1a0) never set `storing`.
        .equ SER_BODY,    0x28cb9170
        .equ DES_BODY,    0x28cb9850
        .equ FEAC,        0x28c8feac
        .equ FA6C,        0x28c8fa6c
        .global ser_hook, des_hook, st_feac, st_fa6c

        .thumb_func
        .type st_feac, %function
st_feac:
        push    {r4, lr}
        ldr     r3, =dbg
        ldrb    ip, [r3, #0]
        add     ip, ip, #1
        strb    ip, [r3, #0]
        ldr     r4, =state
        movs    r3, #1
        strb    r3, [r4, #4]
        ldr     ip, =FEAC + 1
        blx     ip
        movs    r3, #0
        strb    r3, [r4, #4]
        pop     {r4, pc}

        .thumb_func
        .type st_fa6c, %function
st_fa6c:
        push    {r4, lr}
        ldr     r3, =dbg
        ldrb    ip, [r3, #1]
        add     ip, ip, #1
        strb    ip, [r3, #1]
        ldr     r4, =state
        movs    r3, #1
        strb    r3, [r4, #4]
        ldr     ip, =FA6C + 1
        blx     ip
        movs    r3, #0
        strb    r3, [r4, #4]
        pop     {r4, pc}

@ serializer 0x28cb916c(mgr, stream, flag); stream = {ctx, write(ctx, buf, len)}
        .thumb_func
        .type ser_hook, %function
ser_hook:
        ldr     r3, =state
        ldrb    ip, [r3, #4]
        cmp     ip, #0
        .ifdef  DEBUG
        beq     dbg_emit
        .else
        beq     orig_ser                @ (no debug key for the editor in a non-debug build)
        .endif
        ldr     r3, =dbg
        ldrb    ip, [r3, #2]
        add     ip, ip, #1
        strb    ip, [r3, #2]
        str     lr, [r3, #52]
        ldr     r3, =state
        push    {r4-r8, lr}
        sub     sp, #8
        mov     r4, r0
        mov     r5, r1
        mov     r6, r2
        mov     r7, r3                  @ state
        ldrb    r0, [r7]                @ holder
        cmp     r0, #3
        it      lo
        movlo   r0, #3
        subs    r0, #3                  @ holder slot 0..2
        movs    r1, #0                  @ mask
        movs    r2, #0                  @ n
        movs    r3, #0                  @ i
5:      cmp     r3, r0
        beq     6f
        adds    ip, r7, r3
        ldrb    ip, [ip, #1]
        cmp     ip, #0
        beq     6f
        movs    ip, #1
        lsl     ip, ip, r3
        orr     r1, r1, ip
        adds    r2, #1
6:      adds    r3, #1
        cmp     r3, #3
        blo     5b
        ldr     r3, =dbg
        strb    r2, [r3, #3]            @ DEBUG n
        cmp     r2, #0
        beq     9f                      @ nothing to keep: stock bytes
        mov     r8, r1                  @ mask
        movw    r3, #RECSZ
        muls    r2, r3, r2
        adds    r2, #6                  @ L = 4 + n*RECSZ + 2 (our 0x0a, the stock 0x86)
        movs    r3, #0x87
        strb    r3, [sp]
        movs    r3, #0x0e
        strb    r3, [sp, #1]
        movs    r3, #0xc5
        strb    r3, [sp, #2]
        lsrs    r3, r2, #8
        strb    r3, [sp, #3]
        strb    r2, [sp, #4]
        ldrb    r3, [r7]
        cmp     r3, #3
        it      lo
        movlo   r3, #3
        strb    r3, [sp, #5]            @ holder
        strb    r1, [sp, #6]            @ mask
        movs    r3, #0
        strb    r3, [sp, #7]
        ldrd    r0, r3, [r5]
        mov     r1, sp
        movs    r2, #8
        blx     r3
        ldrd    r0, r3, [r5]
        mov     r1, sp
        adds    r1, #7
        movs    r2, #1                  @ the 4th state byte (0)
        blx     r3
        movs    r7, #0                  @ i
7:      lsr     r3, r8, r7
        tst     r3, #1
        beq     8f
        ldr     r1, =store
        movw    r2, #RECSZ
        mla     r1, r2, r7, r1
        ldrd    r0, r3, [r5]
        blx     r3
8:      adds    r7, #1
        cmp     r7, #3
        blo     7b
        movs    r3, #0x0a               @ a copy of the key byte, so the stock reader can be handed 0a 86 ..
        strb    r3, [sp]
        ldrd    r0, r3, [r5]
        mov     r1, sp
        movs    r2, #1
        blx     r3
9:      mov     r0, r4
        mov     r1, r5
        mov     r2, r6
        add     sp, #8
        pop     {r4-r8, lr}
        b       orig_ser
@ DEBUG (test builds only): reads that are not saves (POD Go Edit / hx_ctl) start the section with
@ 87 0f c4 41 [64 bytes of dbg] and the stock 86: map(7) {15: bin, ...}.
        .thumb_func
dbg_emit:
        push    {r0-r2, r4, r5, lr}
        mov     r5, r1
        sub     sp, #8
        movs    r3, #0x87
        strb    r3, [sp]
        movs    r3, #0x0f
        strb    r3, [sp, #1]
        movs    r3, #0xc4
        strb    r3, [sp, #2]
        movs    r3, #0x81
        strb    r3, [sp, #3]
        ldrd    r0, r3, [r5]
        mov     r1, sp
        movs    r2, #4
        blx     r3
        ldrd    r0, r3, [r5]
        ldr     r1, =dbg
        movs    r2, #128
        blx     r3
        add     sp, #8
        pop     {r0-r2, r4, r5, lr}
        .thumb_func
orig_ser:
        push.w  {r4-r11, lr}            @ the stock first instruction
        ldr.w   pc, =SER_BODY + 1

@ companion app (docs/research/COMPANION_APP.md): the editor read, command 0x16, carries key 14 (snapshots
@ 5 and 6, as a save writes them) when the request's parameters are exactly {0x7a: 1}. POD Go Edit sends no
@ parameters, so its reads stay stock. app_dec replaces the command's parameter decoder (stock: return 0,
@ parameters ignored); app_rd wraps its handler and sets the "storing" flag (state+4) for that one read.
        .equ RD_HANDLER,  0x28c8b1a0
        .thumb_func
        .type app_dec, %function
app_dec:                                @ r1 = {buf, end, offset of the parameter value}
        ldr     r2, [r1]
        ldr     r3, [r1, #8]
        ldr     r0, [r1, #4]
        add     r2, r2, r3
        adds    r3, #3
        cmp     r3, r0
        bhi     1f
        ldrb    r3, [r2]
        cmp     r3, #0x81               @ fixmap(1)
        bne     1f
        ldrb    r3, [r2, #1]
        cmp     r3, #0x7a
        bne     1f
        ldrb    r3, [r2, #2]
        cmp     r3, #1
        bne     1f
        movs    r0, #1
        b       2f
1:      movs    r0, #0
2:      ldr     r3, =state
        strb    r0, [r3, #5]
        movs    r0, #0
        bx      lr

        .thumb_func
        .type app_rd, %function
app_rd:
        ldr     r3, =state
        ldrb    ip, [r3, #5]
        cmp     ip, #0
        beq     9f
        push    {r4, lr}
        mov     r4, r3
        movs    ip, #0
        strb    ip, [r4, #5]
        movs    ip, #1
        strb    ip, [r4, #4]
        ldr     ip, =RD_HANDLER + 1
        blx     ip
        movs    r3, #0
        strb    r3, [r4, #4]
        pop     {r4, pc}
9:      ldr.w   pc, =RD_HANDLER + 1

@ deserializer 0x28cb984c(mgr, buf, len): it resets the manager (reset_hook empties the store) first,
@ so the store is filled after it returns.
        .thumb_func
        .type des_hook, %function
des_hook:
        ldr     r3, =dbg
        ldrb    ip, [r3, #4]
        add     ip, ip, #1
        strb    ip, [r3, #4]
        str     r2, [r3, #8]
        str     lr, [r3, #48]
        ldr     ip, [r1]
        str     ip, [r3, #16]
        ldr     ip, [r1, #4]
        str     ip, [r3, #20]
        ldr     ip, [r1, #8]
        str     ip, [r3, #24]
        ldr     ip, [r1, #12]
        str     ip, [r3, #28]
        cmp     r2, #12
        blo     orig_des
        ldrb    r3, [r1]                @ both loaders (0x28c90290, 0x28c90540) start at key 10
        cmp     r3, #0x0a
        bne     orig_des
        ldrb    r3, [r1, #1]
        cmp     r3, #0x87
        bne     orig_des
        ldrb    r3, [r1, #2]
        cmp     r3, #0x0e
        bne     orig_des
        ldrb    r3, [r1, #3]
        cmp     r3, #0xc5
        bne     orig_des
        push    {r4-r10, lr}
        ldr     r3, =dbg
        ldrb    ip, [r3, #5]
        add     ip, ip, #1
        strb    ip, [r3, #5]
        mov     r4, r0
        mov     r5, r1
        mov     r6, r2
        ldrb    r3, [r5, #4]
        ldrb    r7, [r5, #5]
        orr     r7, r7, r3, lsl #8      @ L; payload at buf+6, our 0x0a at buf+4+L, the stock 0x86 after it
        adds    r3, r7, #4
        add     ip, r3, #1
        cmp     ip, r6
        bhs     1f
        ldrb    ip, [r5, r3]
        cmp     ip, #0x0a
        bne     1f
        add     ip, r3, #1
        ldrb    ip, [r5, ip]
        cmp     ip, #0x86
        beq     2f
1:      mov     r0, r4                  @ not ours after all: stock as is
        mov     r1, r5
        mov     r2, r6
        pop     {r4-r10, lr}
        b       orig_des
2:      mov     r0, r4
        adds    r1, r5, r3
        subs    r2, r6, r3
        bl      orig_des
        mov     r8, r0
        ldr     r3, =dbg
        str     r0, [r3, #12]
        cmp     r0, #0
        blt     9f
        ldrb    r0, [r5, #6]            @ holder
        cmp     r0, #3
        blo     9f
        cmp     r0, #5
        bhi     9f
        ldrb    r1, [r5, #7]            @ mask
        movs    r2, #6                  @ check L = 6 + popcount(mask) * RECSZ
        movw    r3, #RECSZ
        lsrs    ip, r1, #1
        tst     r1, #1
        it      ne
        addne   r2, r3
        tst     ip, #1
        it      ne
        addne   r2, r3
        lsrs    ip, ip, #1
        tst     ip, #1
        it      ne
        addne   r2, r3
        cmp     r2, r7
        bne     9f
        adds    r0, r4, #4
        ldr     ip, =LOCK + 1
        blx     ip
        ldr     r6, =state
        ldrb    r0, [r5, #6]
        strb    r0, [r6]                @ holder
        ldrb    r7, [r5, #7]            @ mask
        add     r5, r5, #10             @ first record
        movs    r9, #0                  @ i
4:      lsr     r3, r7, r9
        ands    r3, r3, #1
        adds    r2, r6, r9
        strb    r3, [r2, #1]            @ valid[i]
        cbz     r3, 5f
        ldr     r0, =store
        movw    r2, #RECSZ
        mla     r0, r2, r9, r0
        mov     r1, r5
        ldr     ip, =MEMCPY + 1
        blx     ip
        add     r5, r5, #RECSZ
5:      add     r9, r9, #1
        cmp     r9, #3
        blo     4b
        adds    r0, r4, #4
        ldr     ip, =UNLOCK + 1
        blx     ip
        ldr     r3, =dbg
        ldrb    ip, [r3, #6]
        add     ip, ip, #1
        strb    ip, [r3, #6]
9:      mov     r0, r8
        pop     {r4-r10, pc}
        .thumb_func
orig_des:
        push.w  {r4-r11, lr}            @ the stock first instruction
        ldr.w   pc, =DES_BODY + 1

        .ltorg

@ ---- knobs set per snapshot, or no longer: the stock code changes all four records; mirror it on the store
@ 0x28cb7944 / 0x28cb8040 add / remove a 7-byte entry, 0x28cb8240 / 0x28cb84a8 add / remove a 9-byte entry
@ (all four records, counts at +0xa49 / +0xa4a). Each is run as usual, then once more on `shadow`, a copy of
@ the manager (from before the call) whose records 1-3 hold the store; those records go back to the store.
@ Only when the store has something in it. The shadow has its own mutex (initialised on first use).
@ The same routines also set a value in the current record only (0x28cb7944 when the entry exists): the
@ shadow's current is slot 4's copy (index 3), which is thrown away, so those never reach the store.
        .equ MUTEX_INIT,  0x28c7caac
        .equ MGRSZ,       0xd28
        .global wrap_7944, wrap_8040, wrap_8240, wrap_84a8
        .macro WRAP name, addr, first
        .thumb_func
        .type wrap_\name, %function
wrap_\name:
        ldr     ip, =orig_\name
        b       mirror
        .thumb_func
orig_\name:
        \first                          @ the stock first instruction
        ldr.w   pc, =\addr + 4 + 1
        .endm
        WRAP 7944, 0x28cb7944, "push.w {r4-r10, lr}"
        WRAP 8040, 0x28cb8040, "push.w {r4-r11, lr}"
        WRAP 8240, 0x28cb8240, "push.w {r4-r11, lr}"
        WRAP 84a8, 0x28cb84a8, "push.w {r4-r11, lr}"

        .thumb_func
mirror: orr     ip, ip, #1
        push    {r4-r10, lr}
        mov     r4, r0
        mov     r5, r1
        mov     r6, r2
        mov     r7, r3
        mov     r8, ip
        ldr     r9, =state
        ldrb    r3, [r9, #1]
        ldrb    ip, [r9, #2]
        orr     r3, r3, ip
        ldrb    ip, [r9, #3]
        orrs    r3, r3, ip
        bne     1f
        mov     ip, r8                  @ store empty: just the stock call
        pop     {r4-r10, lr}
        bx      ip
1:      ldr     r10, =shadow
        ldrb    r3, [r9, #5]
        cbnz    r3, 2f
        add     r0, r10, #4
        ldr     ip, =MUTEX_INIT + 1
        blx     ip
        movs    r3, #1
        strb    r3, [r9, #5]
2:      adds    r0, r4, #4
        ldr     ip, =LOCK + 1
        blx     ip
        ldr     r3, [r4]
        str     r3, [r10]
        add     r0, r10, #0xc
        add     r1, r4, #0xc
        movw    r2, #MGRSZ - 0xc
        ldr     ip, =MEMCPY + 1
        blx     ip
        movs    r3, #3                  @ the shadow's current record is slot 4's copy, thrown away: these
        strb.w  r3, [r10, #CUR]         @ routines also write the current record alone (a value change)
        adds    r0, r4, #4
        ldr     ip, =UNLOCK + 1
        blx     ip
        mov     r0, r4                  @ the stock call on the manager
        mov     r1, r5
        mov     r2, r6
        mov     r3, r7
        blx     r8
        mov     r9, r0
        add     r0, r10, #0xc           @ shadow records 1-3 <- store
        ldr     r1, =store
        movw    r2, #3 * RECSZ
        ldr     ip, =MEMCPY + 1
        blx     ip
        mov     r0, r10                 @ the same call on the shadow
        mov     r1, r5
        mov     r2, r6
        mov     r3, r7
        blx     r8
        adds    r0, r4, #4
        ldr     ip, =LOCK + 1
        blx     ip
        ldr     r0, =store
        add     r1, r10, #0xc
        movw    r2, #3 * RECSZ
        ldr     ip, =MEMCPY + 1
        blx     ip
        ldr     r3, =dbg                @ DEBUG: count mirrors
        ldrb    ip, [r3, #7]
        add     ip, ip, #1
        strb    ip, [r3, #7]
        adds    r0, r4, #4
        ldr     ip, =UNLOCK + 1
        blx     ip
        mov     r0, r9
        pop     {r4-r10, pc}
        .ltorg

@ ---- step (c): six-snapshot mode on the footswitches and the screen -----------------------------------------
@ Holding MODE (switch 0x0f) turns six mode on or off (its release is swallowed). In six mode and the
@ snapshot footswitch mode, the six switches select snapshots 1-3 (bottom row) and 4-6 (top row): Bank Up /
@ Down (0x0c / 0x10) are handled here, the other four by the stock handler through `sh_fs` (its table pointer
@ at 0x28cad3f8 points here). The footswitch screen (0x28c9a320) reads its tile tables through pointers that
@ point at the sh_ copies below, filled on each draw: the stock tables, or in six mode the six layout. New
@ tile images (ids 546..557) are served from the cave by the image record / Entry 8 lookups.
        .equ UI_OBJ,      0x28c5e80c
        .equ DRAW_BODY,   0x28c9a324
        .equ GET_MGR,     0x28c5e87c
        .equ UI_DRAW,     0x28c9a320
        .equ GET_NAME,    0x28cb8dc4
        .equ GET_CUR,     0x28cb8d5c
        .equ SELECT,      0x28cb88a4
        .equ FS_BODY,     0x28cae5c0
        .equ MASK_BACK,   0x28c9aa86
        .equ REC_BODY,    0x28c7d49e
        .equ IDX_BODY,    0x28c7d5b8
        .equ IDX_STATE,   0x2828a12c
        .equ OPEN_BODY,   0x28c7d60c
        .equ IMG_ID0,     546
        .equ NIMG,        24
        .equ SYNTH,       0x40000000     @ an Entry 8 offset of a tile drawn here (snap6_ui.py), image k in bits 20..25
        .equ MARK,        0x0001         @ a badge pixel that takes the tile's background colour
        .equ TD,          0              @ tiles.bin: tile descriptions {u16 W, u8 snapshot, u8 sel, u8 badge, u8 dx, u8 dy, 0}
        .equ TINT,        8 * NIMG       @ {idle, active} RGB565 per LED colour 0..11
        .equ BHEAD,       TINT + 48      @ badges {u8 w, u8 h, u16 0, u32 offset}
        .equ BPIX,        BHEAD + 144    @ 18 badges: 1-6 idle (white), 1-6 selected, 1-6 idle as stock (Auto)
        .equ REFRESH,     0x28c5e938     @ called after the screen is redrawn (as 0x28cacc9c does)
        .equ SNAP_LEDS,   0x28cac230     @ snapshot-mode LEDs
        .equ GET_COLOR,   0x28cb8894     @ (mgr, idx): record + 0x27c, the snapshot's colour
        .equ ENT8_0,      0x1000
        .global fs_hook, draw_hook, cur_virt, cur_true, vcolor, vname, mask_stub, rec_hook, idx_hook, open_hook

@ is the footswitch mode snapshots? The footswitch page's state (0x2811ec58: made with its handler 0x28cae5bc at
@ 0x28c5faf6, which gets it as r1) byte +0x3c: 1 stomp, 2 snapshot, 3 preset (0x28cae74e picks the handler by it).
@ r0 = 1 or 0. (Setting 0x14, read first, is "Snapshot Mode Switches"; 0x28121948 + 0x3c is not the mode.)
        .equ FS_STATE,    0x2811ec58
        .thumb_func
fs_is_snap:
        ldr     r0, =FS_STATE
        ldrb    r0, [r0, #0x3c]
        cmp     r0, #2
        ite     eq
        moveq   r0, #1
        movne   r0, #0
        bx      lr

@ the stock handler's switch table (id - 0x0d): stock, or six mode's
        .thumb_func
six_apply:
        push    {r4, lr}
        ldr     r0, =six
        ldrb    r4, [r0]
        ldr     r1, =fs_stock
        cbz     r4, 1f
        ldr     r1, =fs_six
1:      ldr     r0, =sh_fs
        movs    r2, #24
        ldr     ip, =MEMCPY + 1
        blx     ip
        ldr     r1, =led_stock          @ and the snapshot LEDs' table
        cbz     r4, 2f
        ldr     r1, =led_six
2:      ldr     r0, =sh_led
        movs    r2, #8
        ldr     ip, =MEMCPY + 1
        blx     ip
        pop     {r4, pc}

@ six mode now? (six mode on and the snapshot footswitch mode). r0 = 1 or 0. Clobbers r0, r3.
        .thumb_func
six_now:
        ldr     r3, =six
        ldrb    r0, [r3]
        cbz     r0, 1f
        ldr     r0, =FS_STATE
        ldrb    r0, [r0, #0x3c]
        cmp     r0, #2
        ite     eq
        moveq   r0, #1
        movne   r0, #0
1:      bx      lr

@ footswitch events: r0 = event ([+1] switch, [+4] 1 press, 2 release, 4 hold), r1 = state
        .thumb_func
        .type fs_hook, %function
fs_hook:
        push    {r0, r1, r4-r8, lr}
        mov     r4, r0
        ldrb    r6, [r4, #1]
        ldr     r7, [r4, #4]
        ldr     r3, =dbg                @ DEBUG: the last 8 events at dbg[96..111], next at dbg[125]
        ldrb    r2, [r3, #125]
        add     ip, r3, #96
        add     ip, ip, r2, lsl #1
        strb    r6, [ip]
        strb    r7, [ip, #1]
        adds    r2, #1
        and     r2, r2, #7
        strb    r2, [r3, #125]
        ldr     r8, =six
        cmp     r6, #0x0f
        bne     4f
        cmp     r7, #4                  @ MODE held: six mode on / off, once per hold
        bne     2f
        ldrb    r0, [r8, #2]
        cbnz    r0, swallow
        movs    r0, #1
        strb    r0, [r8, #2]
        ldrb    r0, [r8]
        eor     r0, r0, #1
        strb    r0, [r8]
        cbnz    r0, 3f
        bl      give_back               @ back to four: snapshot 4 into slot 4
3:      bl      six_apply
        ldr     ip, =UI_OBJ + 1
        blx     ip
        ldr     ip, =UI_DRAW + 1
        blx     ip
        ldr     ip, =REFRESH + 1
        blx     ip
        bl      fs_is_snap
        cbz     r0, swallow
        ldr     ip, =SNAP_LEDS + 1
        blx     ip
        b       swallow
2:      cmp     r7, #2                  @ its release after a hold
        bne     pass
        ldrb    r0, [r8, #2]
        cbz     r0, pass
        movs    r0, #0
        strb    r0, [r8, #2]
        b       swallow
4:      ldrb    r0, [r8]                @ Bank Up / Down in six mode, snapshot footswitch mode
        cbz     r0, pass
        cmp     r6, #0x0c
        beq     5f
        cmp     r6, #0x10
        bne     pass
5:      bl      fs_is_snap
        cbz     r0, pass
        cmp     r7, #1
        bne     swallow
        ldr     ip, =GET_MGR + 1
        blx     ip
        cmp     r6, #0x0c
        ite     eq
        moveq   r1, #3
        movne   r1, #0
        ldr     ip, =SELECT + 1
        blx     ip
swallow:
        pop     {r0, r1, r4-r8, pc}
pass:   pop     {r0, r1, r4-r8, lr}
        push    {r4, r5, r6, r7, lr}    @ the stock first two instructions
        mov     r4, r1
        ldr.w   pc, =FS_BODY + 1

@ the footswitch screen: fill the sh_ tables, then the stock draw
        .thumb_func
        .type draw_hook, %function
draw_hook:
        push    {r0-r6, lr}
        ldr     r4, =six
        bl      six_now
        mov     r5, r0
        strb    r5, [r4, #1]            @ six mode on this screen
        ldr     r3, =dbg                @ DEBUG: dbg[112] six, [113] on this screen, [114] footswitch mode
        ldrb    r0, [r4]
        strb    r0, [r3, #112]
        strb    r5, [r3, #113]
        ldr     r0, =FS_STATE
        ldrb    r0, [r0, #0x3c]
        strb    r0, [r3, #114]
        adds    r3, #115                @ [115] draws, mod 256
        ldrb    r0, [r3]
        adds    r0, #1
        strb    r0, [r3]
        ldr     r6, =copies
2:      ldr     r0, [r6]                @ {dest, stock, six or 0, bytes}
        cbz     r0, 3f
        ldr     r1, [r6, #4]
        ldr     r3, [r6, #8]
        cmp     r5, #0
        it      ne
        cmpne   r3, #0
        it      ne
        movne   r1, r3                  @ six mode and a six table: it; else the stock one
        ldr     r2, [r6, #12]
        cbz     r1, 4f                  @ (none: nothing to copy)
        ldr     ip, =MEMCPY + 1
        blx     ip
4:      adds    r6, #16
        b       2b
3:      cbnz    r5, 9f                  @ four snapshots: the coloured tiles (images 16-19, selected 20-23)
        ldr     r0, =sh_snap            @ tile -> snapshot (stock {-, 2, 3, -, 0, 1})
        ldr     r1, =sh_img             @ per tile
        movs    r2, #0
7:      ldrb    r3, [r0, r2]
        cmp     r3, #4
        bhs     8f
        addw    r3, r3, #IMG_ID0 + 16
        str     r3, [r1, r2, lsl #2]
8:      adds    r2, #1
        cmp     r2, #6
        blo     7b
        ldr     r1, =sh_sel             @ per snapshot
        movs    r2, #0
7:      addw    r3, r2, #IMG_ID0 + 20
        str     r3, [r1, r2, lsl #2]
        adds    r2, #1
        cmp     r2, #4
        blo     7b
9:      pop     {r0-r6, lr}
        push.w  {r4-r11, lr}            @ the stock first instruction
        ldr.w   pc, =DRAW_BODY + 1

@ the current snapshot for the screen (bl at 0x28c9a914) and the LEDs (0x28cac23a): 4, 5 or 6 for slot 4 in six
@ mode now (their tables have six entries then), else the stock 0..3
        .thumb_func
        .type cur_virt, %function
cur_virt:
        push    {r4, lr}
        ldr     ip, =GET_CUR + 1
        blx     ip
        mov     r4, r0
        bl      six_now
        cbz     r0, 1f
        cmp     r4, #3
        bne     1f
        ldr     r3, =state
        ldrb    r4, [r3]
        cmp     r4, #3
        it      lo
        movlo   r4, #3
1:      mov     r0, r4
        pop     {r4, pc}

@ the current snapshot for the top-right icon (0x28c9b246, 0x28c9b98e, 0x28c9c5c8): always the true one, 0..5
        .thumb_func
        .type cur_true, %function
cur_true:
        push    {r4, lr}
        ldr     ip, =GET_CUR + 1
        blx     ip
        cmp     r0, #3
        bne     1f
        ldr     r3, =state
        ldrb    r0, [r3]
        cmp     r0, #3
        it      lo
        movlo   r0, #3
1:      pop     {r4, pc}

@ a snapshot's colour for the LEDs (bl at 0x28cac264, 0x28cac29e): r0 = manager, r1 = 0..5. Six mode now: 4-6 from
@ slot 4 or the store; four mode: 4 and 5 (the Bank LEDs' entries) have none, so they stay off.
        .thumb_func
        .type vcolor, %function
vcolor: cmp     r1, #3
        blo     3f
        push    {r0, r1, r4, lr}
        bl      six_now
        mov     r4, r0
        pop     {r0, r1}
        cbnz    r4, 1f
        cmp     r1, #3                  @ four mode: 3 is slot 4, 4 and 5 none
        beq     2f
        movs    r0, #0
        pop     {r4, pc}
1:      ldr     r3, =state
        ldrb    r2, [r3]
        cmp     r2, #3
        it      lo
        movlo   r2, #3
        cmp     r1, r2
        bne     4f
2:      movs    r1, #3                  @ the one in slot 4
        pop     {r4, lr}
3:      ldr     ip, =GET_COLOR + 1
        bx      ip
4:      subs    r2, r1, #3
        adds    ip, r3, r2
        ldrb    ip, [ip, #1]
        movs    r0, #0
        cmp     ip, #0
        beq     5f
        ldr     r0, =store
        movw    r3, #RECSZ
        mla     r0, r3, r2, r0
        ldrb.w  r0, [r0, #0x27c]
5:      pop     {r4, pc}

@ a tile's name (bl at 0x28c9aa58): r0 = manager, r1 = snapshot 0..5
        .thumb_func
        .type vname, %function
vname:  cmp     r1, #3
        blo     3f
        ldr     r3, =state
        ldrb    r2, [r3]
        cmp     r2, #3
        it      lo
        movlo   r2, #3
        cmp     r1, r2
        bne     1f
        movs    r1, #3                  @ the one in slot 4
        b       3f
1:      subs    r2, r1, #3
        adds    ip, r3, r2
        ldrb    ip, [ip, #1]
        cmp     ip, #0
        beq     2f
        ldr     r0, =store
        movw    r3, #RECSZ
        mla     r0, r3, r2, r0
        addw    r0, r0, #NAME
        bx      lr
2:      ldr     r0, =defnames           @ not made yet
        movs    r3, #12
        mla     r0, r3, r2, r0
        bx      lr
3:      ldr     ip, =GET_NAME + 1
        bx      ip

@ the tile loop's skip mask (b.w at 0x28c9aa82 for `movs r3, #9; lsrs r3, r5`): none in six mode
        .thumb_func
mask_stub:
        ldr     r3, =six
        ldrb    r3, [r3, #1]
        cmp     r3, #0
        ite     eq
        moveq   r3, #9
        movne   r3, #0
        lsrs    r3, r5
        ldr.w   pc, =MASK_BACK + 1

@ image record (0x28c7d498: r0 = id, r1 = 48-byte record out)
        .thumb_func
        .type rec_hook, %function
rec_hook:
        cbz     r1, 9f
        subw    r2, r0, #IMG_ID0
        cmp     r2, #NIMG
        bhs     1f
        push    {r4, lr}
        mov     r0, r1
        ldr     r1, =img_recs
        movs    r3, #48
        mla     r1, r3, r2, r1
        movs    r2, #48
        ldr     ip, =MEMCPY + 1
        blx     ip
        movs    r0, #0
        pop     {r4, pc}
1:      adds    r2, r0, #1              @ the stock checks
        beq     9f
        ldr.w   pc, =REC_BODY + 1
9:      mvn     r0, #2
        bx      lr

@ Entry 8 index -> {size, offset} (0x28c7d5b4: r0 = index, r1 = out); ours get offset | 0x80000000
        .thumb_func
        .type idx_hook, %function
idx_hook:
        sub     r2, r0, #ENT8_0
        cmp     r2, #NIMG
        bhs     1f
        ldr     r3, =img_ents
        add     r3, r3, r2, lsl #3
        ldr     r2, [r3]
        str     r2, [r1]
        ldr     r2, [r3, #4]
        orr     r2, r2, #0x80000000
        str     r2, [r1, #4]
        movs    r0, #0
        bx      lr
1:      push    {r4, r5, r6, lr}        @ the stock first two instructions
        ldr     r4, =IDX_STATE
        ldr.w   pc, =IDX_BODY + 1

@ open Entry 8 at {size, offset} (0x28c7d608: r0 = size, r1 = offset, r2 = file out, r3 = size out)
        .thumb_func
        .type open_hook, %function
open_hook:
        tst     r1, #0x80000000
        beq     1f
        cbz     r2, 9f
        cbz     r3, 9f
        str     r0, [r3]
        ldr     ip, =ffile
        bic     r1, r1, #0x80000000
        str     r1, [ip, #4]
        str     ip, [r2]
        movs    r0, #0
        bx      lr
9:      mvn     r0, #2
        bx      lr
1:      push    {r4, r5, r6, lr}        @ the stock first two instructions
        sub     sp, #8
        ldr.w   pc, =OPEN_BODY + 1

@ a file over img_pix: read(file, buf, n), write, seek(file, offset, whence), flush
        .thumb_func
ff_read:
        push    {r4-r11, lr}
        ldr     r3, [r0, #4]
        add     r4, r3, r2
        str     r4, [r0, #4]
        tst     r3, #SYNTH
        bne     ff_tile
        mov     r4, r2
        mov     r0, r1
        ldr     r1, =img_pix
        add     r1, r3
        ldr     ip, =MEMCPY + 1
        blx     ip
        mov     r0, r4
        pop     {r4-r11, pc}
@ a snapshot tile, drawn as it is read: the badge where it sits, the snapshot's LED colour (snap6_ui.colours)
@ everywhere else. Pixels are RGB565 little-endian, rows mirrored left-right, as Entry 8 keeps them.
ff_tile:
        mov     r10, r2                 @ n (returned)
        mov     r4, r1                  @ out
        ubfx    r5, r3, #20, #6         @ k
        bfc     r3, #20, #12
        mov     r6, r3                  @ offset in the image
        ldr     r7, =img_tiles
        add     r7, r7, r5, lsl #3      @ its description
        ldrh    r8, [r7]                @ W
        ldrb    r11, [r7, #2]           @ snapshot 0..5
        ldr     ip, =GET_MGR + 1
        blx     ip
        mov     r1, r11
        bl      vcolor                  @ its LED colour (as the LEDs get it; 5 and 6 from the store)
        cmp     r0, #12
        it      hs
        movhs   r0, #0
        ldrb    r9, [r7, #3]            @ selected
        ldr     r1, =img_tiles + TINT
        add     r1, r1, r0, lsl #2
        add     r1, r1, r9, lsl #1
        ldrh    r11, [r1]               @ background
        ldrb    r1, [r7, #4]            @ badge
        orrs    r0, r0, r9
        it      eq
        addeq   r1, #12                 @ Auto and idle: the stock grey badge
        mov     r0, r1
        ldr     r1, =img_tiles + BHEAD
        add     r1, r1, r0, lsl #3
        ldrb    r2, [r1]                @ badge w
        ldrb    r3, [r1, #1]            @ badge h
        ldr     r0, [r1, #4]
        ldr     r1, =img_tiles + BPIX
        add     r9, r1, r0              @ badge pixels
        ldrb    r5, [r7, #5]            @ badge x
        ldrb    r7, [r7, #6]            @ badge y
        mov     lr, r10
1:      cmp     lr, #0
        beq     3f
        lsr     r0, r6, #1              @ pixel
        udiv    r1, r0, r8              @ row
        mls     r0, r1, r8, r0
        sub     r0, r8, r0
        subs    r0, #1                  @ column (mirrored)
        subs    r0, r0, r5
        subs    r1, r1, r7
        mov     ip, r11
        cmp     r0, r2
        bhs     2f
        cmp     r1, r3
        bhs     2f
        mla     r0, r1, r2, r0
        ldrh    r0, [r9, r0, lsl #1]
        cmp     r0, #MARK
        it      ne
        movne   ip, r0
2:      tst     r6, #1
        it      ne
        lsrne   ip, ip, #8
        strb    ip, [r4], #1
        adds    r6, #1
        subs    lr, #1
        b       1b
3:      mov     r0, r10
        pop     {r4-r11, pc}
        .thumb_func
ff_seek:
        cmp     r2, #0
        ittee   eq
        biceq   r1, r1, #0x80000000
        streq   r1, [r0, #4]
        ldrne   r3, [r0, #4]
        addne   r3, r1
        it      ne
        strne   r3, [r0, #4]
        movs    r0, #0
        bx      lr
        .thumb_func
ff_nop: movs    r0, #0
        bx      lr
        .ltorg

        .align  2
ff_vt:  .word   ff_read, ff_nop, ff_seek, ff_nop
ffile:  .word   ff_vt, 0
six:    .byte   0, 0, 0, 0              @ six mode, six mode on this screen, MODE hold seen
defnames: .asciz "SNAPSHOT 4\0"
        .asciz  "SNAPSHOT 5\0"
        .asciz  "SNAPSHOT 6\0"
        .align  2
fs_stock: .word 2, 3, 0, 0, 0, 1        @ 0x28ce239c: switches 0x0d 0x0e - 0x10 0x11 0x12
fs_six:   .word 4, 5, 0, 0, 1, 2
sh_fs:    .word 2, 3, 0, 0, 0, 1
led_stock: .byte 6, 7, 3, 4, 2, 5, 0, 0  @ 0x28ce23ec (snapshot -> LED), then the Bank LEDs (kept off)
led_six:  .byte 5, 6, 7, 2, 3, 4, 0, 0   @ bottom row 5 6 7 = 1 2 3, top row 2 3 4 = 4 5 6
sh_led:   .byte 6, 7, 3, 4, 2, 5, 0, 0
icon_n:   .word 426, 112, 281, 442, IMG_ID0 + 12, IMG_ID0 + 13  @ 0x280110a4 / c4: Icon_Snapshot1..4, 5, 6
icon_r:   .word 354, 268, 86, 56, IMG_ID0 + 14, IMG_ID0 + 15    @ 0x280110b4 / d4: the Red ones
sh_x:   .space  24
sh_y:   .space  24
sh_tx:  .space  48
sh_ty:  .space  48
sh_img: .space  24
sh_snap: .space 8
sh_c2t: .space  8
sh_sel: .space  24
six_x:  .word   5, 164, 323, 5, 164, 323
six_tx: .word   82, 241, 400, 82, 241, 400
six_img: .word  IMG_ID0 + 3, IMG_ID0 + 4, IMG_ID0 + 5, IMG_ID0 + 0, IMG_ID0 + 1, IMG_ID0 + 2
six_snap: .byte 3, 4, 5, 0, 1, 2, 0, 0
six_c2t: .byte  3, 4, 5, 0, 1, 2, 0, 0
six_sel: .word  IMG_ID0 + 6, IMG_ID0 + 7, IMG_ID0 + 8, IMG_ID0 + 9, IMG_ID0 + 10, IMG_ID0 + 11
@ {dest, stock, six, bytes}: six mode copies `six` (or `stock` when six is 0), else `stock` (skipped when 0).
@ six_tx then overwrites the first six of sh_tx's 12 words. 0x28ce12a0 has four words: six reads two past it.
copies: .word   sh_x, 0x28ce11dc, six_x, 24
        .word   sh_y, 0x28ce11f4, 0, 24
        .word   sh_tx, 0x28ce1224, 0, 48
        .word   sh_tx, 0, six_tx, 24
        .word   sh_ty, 0x28ce1254, 0, 48
        .word   sh_img, 0x28ce12b0, six_img, 24
        .word   sh_snap, 0x28ce12f8, six_snap, 8
        .word   sh_c2t, 0x28ce1284, six_c2t, 8
        .word   sh_sel, 0x28ce12a0, six_sel, 24
        .word   0

        .align  2
names:  .asciz  "SNAPSHOT 5\0"
        .asciz  "SNAPSHOT 6\0"

        .align  2
state:  .byte   0, 0, 0, 0              @ holder, valid[3]
        .byte   0, 0, 0, 0              @ storing (set while a preset is written to the unit's store);
                                        @ +5: the companion app asked for key 14 on the next read
        .align  2
dbg:    .space  128                     @ DEBUG (test builds): see dbg_emit
        .align  2
store:  .space  3 * RECSZ
tmp:    .space  RECSZ                   @ slot 3 while it is lent (sel_hook)
        .align  3
shadow: .space  MGRSZ                   @ a manager for mirroring onto the store (mirror)

@ the new tile images (podgo/snap6_ui.py, from the user's own firmware; build/snap6_img, never published)
        .align  2
img_recs: .incbin "recs.bin"
img_ents: .incbin "ents.bin"
img_tiles: .incbin "tiles.bin"
img_pix:  .incbin "pix.bin"
