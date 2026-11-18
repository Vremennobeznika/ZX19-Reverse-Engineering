/* Bounds are limited to bytes occupied by the verified stock APP image.
 * This is not a complete board linker script or a whole-flash map.
 */
MEMORY {
    APP_CODE (rx) : ORIGIN = 0x82c400, LENGTH = 346948
    APP_STATIC (rw) : ORIGIN = 0x208500, LENGTH = 0x8a30
}
ENTRY(r19z_system_init)
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
