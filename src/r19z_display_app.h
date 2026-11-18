#ifndef R19Z_DISPLAY_APP_H
#define R19Z_DISPLAY_APP_H
#include "r19z_panel.h"

typedef struct {
    watch_lcd lcd;
    watch_state watch;
    uint8_t shown_day, shown_month;
} r19z_display_app;

/* Board clock snapshot. day and month use the local calendar. */
typedef struct {
    uint32_t monotonic_ms, local_seconds;
    uint8_t day, month;
} r19z_clock_sample;

/* Start with zero-initialized app storage and initialized platform services. */
int r19z_display_start(r19z_display_app *, const r19z_clock_sample *);
int r19z_display_update(r19z_display_app *, const r19z_clock_sample *);
#endif
