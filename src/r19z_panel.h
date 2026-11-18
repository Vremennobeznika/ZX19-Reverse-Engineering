#ifndef R19Z_PANEL_H
#define R19Z_PANEL_H
#include "watch_lcd.h"

/* First panel variant only. Caller owns the enabled display bus exclusively
 * and supplies power, peripheral clock, pinmux and a working delay routine. */
int r19z_panel_start(watch_lcd *lcd, watch_lcd_delay_fn delay);
/* Use after the R19Z runtime has installed its delay service. */
int r19z_panel_start_platform(watch_lcd *lcd);
#endif
