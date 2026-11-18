#ifndef ZX19_WATCH_RENDER_H
#define ZX19_WATCH_RENDER_H
#include "watch_core.h"
typedef void (*watch_fill_fn)(void *, int, int, int, int, uint16_t);
typedef struct { int width, height; watch_fill_fn fill; void *context; } watch_canvas;
/* No framebuffer or heap. fill must synchronously consume each clipped rectangle. */
WATCH_API void watch_render(const watch_state *, const watch_canvas *, unsigned dirty,
                            unsigned local_seconds, unsigned day, unsigned month);
/* Same layout, restricted to [top, bottom); invalid region emits no writes. */
WATCH_API void watch_render_region(const watch_state *, const watch_canvas *, unsigned dirty,
                                  unsigned local_seconds, unsigned day, unsigned month,
                                  int top, int bottom);
#endif
