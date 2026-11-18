#include "r19z_pins.h"
#include "r19z_i2c.h"

#define WORD(address) (*(volatile uint32_t *)(uintptr_t)(address))
#define I2C(offset) WORD(0x40015400u + (offset))

/* Exclusive cold-start configuration for the R19Z touch bus. The stock
 * firmware uses a 20 MHz input and a 400 kHz fast-mode configuration. */
void r19z_touch_setup(void) {
    r19z_select_pin(38, 7);
    r19z_select_pin(37, 8);
    r19z_configure_pad(0x98, 4, 3);
    r19z_configure_pad(0x96, 4, 3);
    r19z_configure_pad(0x86, 7, 1);
    WORD(0x40000218u) |= 0x20000u;
    WORD(0x40000238u) |= 0xcu;
    I2C(0x6c) = 0;
    I2C(0x00) = 0x65;
    I2C(0x04) = 0x15;
    I2C(0x7c) = 1;
    I2C(0x3c) = 0;
    I2C(0x38) = 0;
    I2C(0x1c) = 20;
    I2C(0x20) = 27;
    I2C(0x30) = 0;
    I2C(0x6c) = 1;
}
