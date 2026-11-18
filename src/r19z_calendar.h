#ifndef R19Z_CALENDAR_H
#define R19Z_CALENDAR_H
#include "r19z_display_app.h"

typedef struct {
    uint32_t last_ms, seconds;
    uint16_t year, fraction_ms;
    uint8_t month, day;
} r19z_calendar;

/* QC time command, local civil time; the sender already applied its zone. */
int r19z_calendar_accept(r19z_calendar *, const uint8_t *, size_t, uint32_t now);
void r19z_calendar_sample(r19z_calendar *, uint32_t now, r19z_clock_sample *);
#endif
