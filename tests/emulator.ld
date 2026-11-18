/* Synthetic test addresses only. NEVER use as a ZX19 flash layout. */
ENTRY(watch_init)
SECTIONS {
  . = 0x100000;
  .text : { *(.text*) *(.rodata*) }
  .ARM.exidx : { *(.ARM.exidx*) }
  . = 0x200000;
  .data : { *(.data*) }
  .bss : { *(.bss*) *(COMMON) }
}
