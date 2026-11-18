#include "watch_core.h"
#define WATCH_MAX_STOPWATCH_MS 359999000u

static void advance(watch_state *s, uint32_t now) {
    uint32_t elapsed = now - s->last_ms;
    uint32_t old_timer = s->timer_ms / 1000u;
    uint32_t old_stopwatch = s->stopwatch_ms / 1000u;
    s->last_ms = now;
    if (s->timer_running) {
        if (elapsed >= s->timer_ms) {
            s->timer_ms = 0;
            s->timer_running = 0;
            s->alarm_pending = 1;
            if (s->page==WATCH_TIMER) s->dirty=WATCH_FULL;
        } else s->timer_ms -= elapsed;
    }
    if (s->stopwatch_running) {
        if (elapsed >= WATCH_MAX_STOPWATCH_MS - s->stopwatch_ms) {
            s->stopwatch_ms = WATCH_MAX_STOPWATCH_MS;
            s->stopwatch_running = 0;
            if (s->page==WATCH_STOPWATCH) s->dirty=WATCH_FULL;
        } else s->stopwatch_ms += elapsed;
    }
    if ((s->page == WATCH_TIMER && old_timer != s->timer_ms / 1000u) ||
        (s->page == WATCH_STOPWATCH && old_stopwatch != s->stopwatch_ms / 1000u)) {
        if (!s->dirty) s->dirty = WATCH_VALUES;
    }
}

void watch_init(watch_state *s, uint32_t now) {
    unsigned char *bytes = (unsigned char *)s;
    size_t i;
    for (i = 0; i < sizeof(*s); ++i) bytes[i] = 0;
    s->last_ms = now;
    s->shown_second = UINT32_MAX;
    s->dirty = WATCH_FULL;
}

void watch_tick(watch_state *s, uint32_t now, uint32_t wall_second) {
    advance(s, now);
    if (s->shown_second != wall_second) {
        int minute_changed = s->shown_second/60u != wall_second/60u;
        s->shown_second = wall_second;
        if (s->page == WATCH_FACE && minute_changed && !s->dirty) s->dirty = WATCH_VALUES;
    }
}

int watch_timer_set(watch_state *s, uint32_t seconds, uint32_t now) {
    if (seconds == 0 || seconds > 86400u) return 0;
    advance(s, now);
    s->timer_ms = seconds * 1000u;
    s->timer_preset_s = seconds;
    s->timer_running = 0;
    s->alarm_pending = 0;
    s->dirty = WATCH_FULL;
    return 1;
}

void watch_timer_toggle(watch_state *s, uint32_t now) {
    advance(s, now);
    if (s->timer_ms) s->timer_running = !s->timer_running;
    s->dirty = WATCH_FULL;
}

void watch_stopwatch_toggle(watch_state *s, uint32_t now) {
    advance(s, now);
    if (s->stopwatch_ms < WATCH_MAX_STOPWATCH_MS)
        s->stopwatch_running = !s->stopwatch_running;
    s->dirty = WATCH_FULL;
}

void watch_stopwatch_reset(watch_state *s, uint32_t now) {
    advance(s, now);
    s->stopwatch_ms = 0;
    s->stopwatch_running = 0;
    s->dirty = WATCH_FULL;
}

void watch_open(watch_state *s, enum watch_page page) {
    if (page < WATCH_FACE || page > WATCH_NOTICES || s->page == page) return;
    s->page = (uint8_t)page;
    s->selected = 0;
    s->dirty = WATCH_FULL;
}

void watch_next(watch_state *s, int direction) {
    unsigned count;
    if (s->page == WATCH_MENU) count = 3;
    else if (s->page == WATCH_NOTICES) count = s->notice_count;
    else return;
    if (!count || !direction) return;
    s->selected = (uint8_t)((s->selected + (direction > 0 ? 1 : count - 1)) % count);
    s->dirty = WATCH_FULL;
}

void watch_select(watch_state *s) {
    if (s->page == WATCH_FACE) watch_open(s, WATCH_MENU);
    else if (s->page == WATCH_MENU) watch_open(s, (enum watch_page)(WATCH_TIMER + s->selected));
}

int watch_notice(watch_state *s, const char *text, size_t n) {
    size_t i = 0, keep = 0;
    size_t limit = n >= WATCH_NOTICE_BYTES ? WATCH_NOTICE_BYTES-4 : WATCH_NOTICE_BYTES-1;
    char *dest;
    if (!text || !n || n > 4096) return 0;
    /* Validate the entire supplied byte sequence before changing existing data. */
    while (i < n) {
        uint32_t cp;
        unsigned count, j;
        unsigned char ch = (unsigned char)text[i];
        if (!ch) return 0;
        if (ch < 0x80) { count = 1; cp = ch; }
        else if (ch >= 0xc2 && ch <= 0xdf) { count = 2; cp = ch & 0x1fu; }
        else if (ch >= 0xe0 && ch <= 0xef) { count = 3; cp = ch & 0x0fu; }
        else if (ch >= 0xf0 && ch <= 0xf4) { count = 4; cp = ch & 7u; }
        else return 0;
        if (count > n - i) return 0;
        for (j = 1; j < count; ++j) {
            ch = (unsigned char)text[i+j];
            if ((ch & 0xc0u) != 0x80u) return 0;
            cp = (cp << 6) | (ch & 0x3fu);
        }
        if ((count == 2 && cp < 0x80) || (count == 3 && cp < 0x800) ||
            (count == 4 && cp < 0x10000) || cp > 0x10ffff ||
            (cp >= 0xd800 && cp <= 0xdfff)) return 0;
        i += count;
        if (i <= limit) keep = i;
    }
    dest = s->notices[s->notice_head];
    for (i = 0; i < keep; ++i) dest[i] = text[i];
    if (n >= WATCH_NOTICE_BYTES) {
        dest[keep++]='.'; dest[keep++]='.'; dest[keep++]='.';
    }
    dest[keep] = 0;
    s->notice_head = (uint8_t)((s->notice_head + 1) % 4);
    if (s->notice_count < 4) ++s->notice_count;
    if (s->page == WATCH_NOTICES || s->page == WATCH_FACE) s->dirty = WATCH_FULL;
    return 1;
}

int watch_take_alarm(watch_state *s) {
    int alarm = s->alarm_pending;
    s->alarm_pending = 0;
    return alarm;
}

uint32_t watch_deadline_ms(const watch_state *s, int display_on) {
    uint32_t result = UINT32_MAX;
    if (s->timer_running) result = s->timer_ms;
    if (display_on && s->page == WATCH_FACE) {
        uint32_t face_wait = s->shown_second==UINT32_MAX ? 1000u : (60u-s->shown_second%60u)*1000u;
        if (result>face_wait) result=face_wait;
    }
    if (display_on && ((s->page == WATCH_TIMER && s->timer_running) ||
        (s->page == WATCH_STOPWATCH && s->stopwatch_running))) {
        if (result > 1000u) result = 1000u;
    }
    return result;
}

uint8_t watch_take_dirty(watch_state *s) {
    uint8_t dirty = s->dirty;
    s->dirty = WATCH_CLEAN;
    return dirty;
}

size_t watch_state_bytes(void) { return sizeof(watch_state); }
