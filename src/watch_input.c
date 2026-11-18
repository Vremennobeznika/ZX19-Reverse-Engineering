#include "watch_input.h"
static int adjust_timer(watch_state *s,int increase,uint32_t now) {
    uint32_t seconds;
    if (s->timer_running) return 0;
    seconds=s->timer_ms/1000u+(s->timer_ms%1000u?1u:0u);
    if (increase) seconds=seconds>86340u?86400u:seconds+60u;
    else seconds=seconds>60u?seconds-60u:1u;
    return watch_timer_set(s,seconds,now);
}

int watch_tap(watch_state *s, int width, int height, int x, int y, uint32_t now) {
    if (!s || width<128 || width>1024 || height<200 || height>1024 ||
        x<0 || y<0 || x>=width || y>=height) return 0;
    if (s->page==WATCH_FACE) { watch_open(s,WATCH_MENU); return 1; }
    if (s->page==WATCH_MENU && x>=8 && x<width-8) {
        unsigned i;
        for (i=0;i<3;++i) {
            int top=58+(int)i*54;
            if (y>=top && y<top+44) {
                watch_open(s,(enum watch_page)(WATCH_TIMER+i));
                if (s->page==WATCH_TIMER && !s->timer_ms) watch_timer_set(s,s->timer_preset_s?s->timer_preset_s:300u,now);
                return 1;
            }
        }
    }
    if (s->page==WATCH_TIMER && height>=260 && x>=8 && x<width-8 && y>=height-140 && y<height-96)
        return adjust_timer(s,x>=width/2,now);
    if (x>=8 && x<width-8 && y>=height-74 && y<height-30) {
        if (s->page==WATCH_TIMER) {
            if (!s->timer_ms) watch_timer_set(s,s->timer_preset_s?s->timer_preset_s:300u,now);
            watch_timer_toggle(s,now); return 1;
        }
        if (s->page==WATCH_STOPWATCH) { watch_stopwatch_toggle(s,now); return 1; }
    }
    return 0;
}

int watch_swipe(watch_state *s, int direction) {
    if (!s || !direction) return 0;
    if (s->page==WATCH_TIMER) return adjust_timer(s,direction<0,s->last_ms);
    if (s->page!=WATCH_MENU && s->page!=WATCH_NOTICES) return 0;
    watch_next(s,direction);
    return 1;
}

void watch_button(watch_state *s, int long_press, uint32_t now) {
    if (!s) return;
    if (long_press) {
        if (s->page==WATCH_STOPWATCH) watch_stopwatch_reset(s,now);
        return;
    }
    if (s->page==WATCH_FACE) watch_open(s,WATCH_MENU);
    else if (s->page==WATCH_MENU) {
        watch_select(s);
        if (s->page==WATCH_TIMER && !s->timer_ms) watch_timer_set(s,s->timer_preset_s?s->timer_preset_s:300u,now);
    } else watch_open(s,WATCH_FACE);
}
