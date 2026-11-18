#ifndef R19Z_I2C_H
#define R19Z_I2C_H
#include <stdint.h>
#include <stddef.h>
typedef struct { uint32_t poll_budget; uint8_t fault; } r19z_i2c_bus;
/* For watch_touch_bus.read. I2C1 must already be clocked, pinned, exclusively
 * owned, configured as master with restart enabled, and targeted at 0x15.
 * Failure latches fault. Reinitialize hardware before clearing it.
 * Budget counts status polls, capped at 4096, not milliseconds.
 * No device test has occurred.
 */
int r19z_touch_i2c_read(void *, uint8_t address, uint8_t reg, uint8_t *, size_t);
#endif
