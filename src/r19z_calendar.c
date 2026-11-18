#include "r19z_calendar.h"

static unsigned month_days(unsigned year, unsigned month) {
    static const uint8_t days[] = {31,28,31,30,31,30,31,31,30,31,30,31};
    return days[month-1] + (month == 2 && year % 4 == 0 &&
                             (year % 100 != 0 || year % 400 == 0));
}

int r19z_calendar_accept(r19z_calendar *c, const uint8_t *p, size_t length, uint32_t now) {
    if (!c || !p || length != 16 || p[0] != 1) return 0;
    uint8_t sum = 0, fields[6];
    for (unsigned i = 0; i < 15; ++i) sum += p[i];
    if (sum != p[15]) return 0;
    for (unsigned i = 0; i < 6; ++i) {
        unsigned tens = p[i+1] >> 4, ones = p[i+1] & 15;
        if (tens > 9 || ones > 9) return 0;
        fields[i] = (uint8_t)(10*tens + ones);
    }
    unsigned year = 2000u + fields[0], month = fields[1], day = fields[2];
    if (!month || month > 12 || !day || day > month_days(year, month) ||
        fields[3] > 23 || fields[4] > 59 || fields[5] > 59) return 0;
    c->year = (uint16_t)year;
    c->month = (uint8_t)month;
    c->day = (uint8_t)day;
    c->seconds = fields[3]*3600u + fields[4]*60u + fields[5];
    c->last_ms = now;
    c->fraction_ms = 0;
    return 1;
}

void r19z_calendar_sample(r19z_calendar *c, uint32_t now, r19z_clock_sample *out) {
    out->monotonic_ms = now;
    if (!c->year) {
        out->local_seconds = UINT32_MAX;
        out->month = out->day = 0;
        return;
    }
    uint32_t delta = now - c->last_ms;
    c->last_ms = now;
    unsigned fraction = c->fraction_ms + delta % 1000u;
    uint32_t seconds = c->seconds + delta / 1000u + fraction / 1000u;
    c->fraction_ms = (uint16_t)(fraction % 1000u);
    c->seconds = seconds % 86400u;
    unsigned day = c->day + seconds / 86400u;
    while (day > month_days(c->year,c->month)) {
        day -= month_days(c->year,c->month);
        if (++c->month == 13) { c->month = 1; ++c->year; }
    }
    c->day = (uint8_t)day;
    out->local_seconds = c->seconds;
    out->month = c->month;
    out->day = c->day;
}
