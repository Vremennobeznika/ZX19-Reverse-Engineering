#ifndef R19Z_PINS_H
#define R19Z_PINS_H
void r19z_configure_pad(unsigned index, unsigned low_bits, unsigned flags);
void r19z_select_pin(unsigned pin, unsigned function);
#endif
