#include "r19z_display_app.h"
#include "watch_render.h"

static int valid_sample(const r19z_clock_sample *t) {
    if (!t) return 0;
    if (t->local_seconds == UINT32_MAX) return !t->day && !t->month;
    return t->local_seconds < 86400 && t->month >= 1 && t->month <= 12 &&
           t->day >= 1 && t->day <= 31;
}

int r19z_display_update(r19z_display_app *app, const r19z_clock_sample *t) {
    if (!app || !valid_sample(t) || app->lcd.fault ||
        !app->lcd.command || !app->lcd.data) return 0;
    watch_tick(&app->watch, t->monotonic_ms, t->local_seconds);
    unsigned dirty = watch_take_dirty(&app->watch);
    if (!dirty && app->watch.page == WATCH_FACE &&
        (app->shown_day != t->day || app->shown_month != t->month)) dirty = WATCH_VALUES;
    if (!dirty) return 1;
    watch_canvas screen = {172, 320, watch_lcd_canvas_fill, &app->lcd};
    watch_render(&app->watch, &screen, dirty, t->local_seconds, t->day, t->month);
    if (app->lcd.fault) {
        app->watch.dirty = WATCH_FULL;
        return 0;
    }
    app->shown_day = t->day;
    app->shown_month = t->month;
    return 1;
}

int r19z_display_start(r19z_display_app *app, const r19z_clock_sample *t) {
    if (!app || !valid_sample(t) || !r19z_panel_start_platform(&app->lcd)) return 0;
    watch_init(&app->watch, t->monotonic_ms);
    return r19z_display_update(app, t);
}
