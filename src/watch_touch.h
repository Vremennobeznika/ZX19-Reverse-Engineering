#ifndef ZX19_WATCH_TOUCH_H
#define ZX19_WATCH_TOUCH_H
#include "watch_input.h"
typedef int (*watch_i2c_read_fn)(void *, uint8_t, uint8_t, uint8_t *, size_t);
typedef struct { void *context; watch_i2c_read_fn read; uint8_t chip_id; } watch_touch_bus;
typedef struct { uint16_t x,y; uint8_t fingers,gesture; } watch_touch_sample;
typedef struct {
    uint32_t started_ms;
    uint16_t start_x,start_y,last_x,last_y,max_dx,max_dy;
    uint8_t active;
} watch_touch_session;
WATCH_API int watch_touch_probe(watch_touch_bus *);
WATCH_API int watch_touch_read(watch_touch_bus *, watch_touch_sample *);
WATCH_API void watch_touch_cancel(watch_touch_session *);
WATCH_API int watch_touch_apply(watch_state *, watch_touch_session *, const watch_touch_sample *, uint32_t now_ms);
#endif
