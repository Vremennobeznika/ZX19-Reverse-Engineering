/* Bounds are limited to bytes occupied by the verified stock APP image.
 * This is not a complete board linker script or a whole-flash map.
 */
MEMORY {
    APP_CODE (rx) : ORIGIN = 0x82c400, LENGTH = 346948
    APP_STATIC (rw) : ORIGIN = 0x208500, LENGTH = 0x8a30
}
ENTRY(r19z_system_init)
/* RTL8762D ROM.lib symbols referenced by the GAP library and OS headers. */
PROVIDE(SystemCall_Stack = 0x202a60);
PROVIDE(os_msg_queue_create_intern = 0x12cdd);
PROVIDE(os_msg_recv_intern = 0x12e2d);
PROVIDE(os_msg_queue_delete_intern = 0x12d39);
PROVIDE(__aeabi_memcpy = 0x3a293);
PROVIDE(__aeabi_memclr4 = 0x3a3d5);
PROVIDE(log_buffer = 0x8037);
SECTIONS {
    .text : {
        KEEP(*(.r19z.entry))
        *(.text*) *(.rodata*)
    } > APP_CODE
    .ARM.exidx : { *(.ARM.exidx*) } > APP_CODE
    .data : {
        __r19z_data_start = .;
        *(.data*)
        __r19z_data_end = .;
    } > APP_STATIC AT> APP_CODE
    __r19z_data_load = LOADADDR(.data);
    .bss (NOLOAD) : {
        __r19z_bss_start = .;
        *(.bss*) *(COMMON)
        __r19z_bss_end = .;
    } > APP_STATIC
    ASSERT(__r19z_bss_end <= 0x210f30, "Static RAM exceeds stock static span")
    ASSERT(LOADADDR(.data)+SIZEOF(.data) <= 0x880f44, "Code exceeds stock image span")
}
