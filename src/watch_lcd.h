#ifndef ZX19_WATCH_LCD_H
#define ZX19_WATCH_LCD_H
#include "watch_core.h"
/* Transport callbacks return nonzero on success and must have bounded hardware timeouts. */
typedef int (*watch_lcd_command_fn)(void *, uint8_t);
typedef int (*watch_lcd_data_fn)(void *, const uint8_t *, size_t);
typedef struct {
    void *context;
    watch_lcd_command_fn command;
    watch_lcd_data_fn data;
    uint8_t fault;
} watch_lcd;
typedef int (*watch_lcd_delay_fn)(void *, unsigned milliseconds);
/* First R19Z panel variant only. Board must select the panel and supply
 * a powered, reset panel, an initialized bus and a bounded delay callback. */
WATCH_API int watch_lcd_init_r19z_first(watch_lcd *, watch_lcd_delay_fn);
/* Select the stock pad configuration (argument to 0x83afd0, not pin voltage). */
typedef int (*watch_lcd_reset_mode_fn)(void *, unsigned mode);
WATCH_API int watch_lcd_start_r19z_first(watch_lcd *, watch_lcd_reset_mode_fn, watch_lcd_delay_fn);
/* Assumes panel and 8080 bus were already correctly initialized by the board adapter.
 * Geometry comes from the first R19Z stock init path. No GPIO or power pins are guessed. */
WATCH_API int watch_lcd_fill(watch_lcd *, int x, int y, int width, int height, uint16_t rgb565);
WATCH_API void watch_lcd_canvas_fill(void *, int, int, int, int, uint16_t);
#endif
