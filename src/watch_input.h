#ifndef ZX19_WATCH_INPUT_H
#define ZX19_WATCH_INPUT_H
#include "watch_core.h"
/* Board adapter supplies normalized display coordinates; no touch controller guessed. */
WATCH_API int watch_tap(watch_state *, int width, int height, int x, int y, uint32_t now_ms);
WATCH_API int watch_swipe(watch_state *, int direction);
WATCH_API void watch_button(watch_state *, int long_press, uint32_t now_ms);
#endif
