/* Original, allocation-free application core. Board drivers are not implemented. */
#ifndef ZX19_WATCH_CORE_H
#define ZX19_WATCH_CORE_H
#include <stdint.h>
#include <stddef.h>
#ifdef _WIN32
#define WATCH_API __declspec(dllexport)
#else
#define WATCH_API
#endif

enum watch_page { WATCH_FACE, WATCH_MENU, WATCH_TIMER, WATCH_STOPWATCH, WATCH_NOTICES };
enum watch_dirty { WATCH_CLEAN = 0, WATCH_VALUES = 1, WATCH_FULL = 2 };
#define WATCH_NOTICE_BYTES 192
typedef struct {
    uint32_t last_ms, timer_ms, stopwatch_ms, shown_second, timer_preset_s;
    uint8_t timer_running, stopwatch_running, alarm_pending, page;
    uint8_t selected, dirty, notice_count, notice_head;
    char notices[4][WATCH_NOTICE_BYTES];
} watch_state;

/* now_ms must be a monotonic 32-bit millisecond clock, sampled at least once per wrap. */
WATCH_API void watch_init(watch_state *s, uint32_t now_ms);
WATCH_API void watch_tick(watch_state *s, uint32_t now_ms, uint32_t wall_second);
WATCH_API int watch_timer_set(watch_state *s, uint32_t seconds, uint32_t now_ms);
WATCH_API void watch_timer_toggle(watch_state *s, uint32_t now_ms);
WATCH_API void watch_stopwatch_toggle(watch_state *s, uint32_t now_ms);
WATCH_API void watch_stopwatch_reset(watch_state *s, uint32_t now_ms);
WATCH_API void watch_open(watch_state *s, enum watch_page page);
WATCH_API void watch_next(watch_state *s, int direction);
WATCH_API void watch_select(watch_state *s);
WATCH_API int watch_notice(watch_state *s, const char *utf8, size_t length);
WATCH_API int watch_take_alarm(watch_state *s);
/* Maximum sleep until next required core event. UINT32_MAX means no scheduled event. */
WATCH_API uint32_t watch_deadline_ms(const watch_state *s, int display_on);
WATCH_API uint8_t watch_take_dirty(watch_state *s);
WATCH_API size_t watch_state_bytes(void);
#endif
