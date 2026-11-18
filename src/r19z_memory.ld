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
PROVIDE(SHA256_Init = 0x38b59);
PROVIDE(SHA256_Update = 0x38b6f);
PROVIDE(SHA256_Final = 0x38bef);
PROVIDE(flash_get_bank_addr = 0xce81);
PROVIDE(flash_get_bank_size = 0xcef9);
PROVIDE(is_ota_support_bank_switch = 0xd9a3);
PROVIDE(flash_sw_protect_unlock_by_addr_locked = 0xd6cf);
PROVIDE(flash_set_block_protect_locked = 0xd6a9);
PROVIDE(flash_erase_locked = 0xcf67);
PROVIDE(flash_write_locked = 0xd3a5);
PROVIDE(flash_read_locked = 0xd415);
PROVIDE(check_image_chksum = 0xd8b1);
PROVIDE(WDG_SystemReset = 0x22b1);
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
    .noinit (NOLOAD) : { *(.noinit) } > APP_STATIC
    ASSERT(__r19z_bss_end <= 0x210f30, "Static RAM exceeds stock static span")
    ASSERT(LOADADDR(.data)+SIZEOF(.data) <= 0x880f44, "Code exceeds stock image span")
}
