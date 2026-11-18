#include "watch_strip.h"

typedef struct { uint16_t *pixels; int first_row; } strip_context;

static void strip_fill(void *context, int x, int y, int w, int h, uint16_t color) {
    strip_context *s = context;
    int bottom = y + h;
    if (y < s->first_row) y = s->first_row;
    if (bottom > s->first_row + WATCH_STRIP_ROWS)
        bottom = s->first_row + WATCH_STRIP_ROWS;
    for (; y < bottom; ++y) {
        uint16_t *row = s->pixels + (y - s->first_row) * WATCH_STRIP_WIDTH + x;
        for (int column = 0; column < w; ++column) row[column] = color;
    }
}

int watch_render_strip(const watch_state *state, uint16_t *pixels,
    size_t capacity_pixels, unsigned first_row, unsigned local_seconds,
    unsigned day, unsigned month) {
    if (!state || !pixels || capacity_pixels < WATCH_STRIP_PIXELS ||
        first_row > 320 - WATCH_STRIP_ROWS || first_row % WATCH_STRIP_ROWS)
        return 0;
    strip_context context = {pixels, (int)first_row};
    watch_canvas canvas = {WATCH_STRIP_WIDTH, 320, strip_fill, &context};
    /* Each reused vendor strip needs all its pixels, including the background. */
    watch_render_region(state, &canvas, WATCH_FULL, local_seconds, day, month,
                        (int)first_row, (int)first_row + WATCH_STRIP_ROWS);
    return 1;
}
