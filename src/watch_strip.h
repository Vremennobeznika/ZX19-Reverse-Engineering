#ifndef ZX19_WATCH_STRIP_H
#define ZX19_WATCH_STRIP_H
#include "watch_render.h"
#define WATCH_STRIP_WIDTH 172
#define WATCH_STRIP_ROWS 10
#define WATCH_STRIP_PIXELS (WATCH_STRIP_WIDTH * WATCH_STRIP_ROWS)
/* Render into a caller-owned RGB565 strip, no heap or persistent storage.
 * State and wall time must be held constant across all 32 strips of a frame.
 * Returns 0 without writes on invalid input. This is not a hardware hook.
 */
WATCH_API int watch_render_strip(const watch_state *state, uint16_t *pixels,
    size_t capacity_pixels, unsigned first_row, unsigned local_seconds,
    unsigned day, unsigned month);
#endif
