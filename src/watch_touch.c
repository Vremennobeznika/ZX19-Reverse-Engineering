#include "watch_touch.h"
static int supported(uint8_t id) { return id==0xb4 || id==0xb5 || id==0xb6; }
static unsigned distance(unsigned a,unsigned b) { return a>b?a-b:b-a; }

int watch_touch_probe(watch_touch_bus *bus) {
    uint8_t id=0;
    if (!bus || !bus->read) return 0;
    bus->chip_id=0;
    if (!bus->read(bus->context,0x15,0xa7,&id,1) || !supported(id)) return 0;
    bus->chip_id=id;
    return 1;
}

int watch_touch_read(watch_touch_bus *bus, watch_touch_sample *sample) {
    uint8_t b[6];
    watch_touch_sample result;
    if (!bus || !sample || !bus->read || !supported(bus->chip_id)) return 0;
    if (!bus->read(bus->context,0x15,1,b,6)) return 0;
    result.gesture=b[0]; result.fingers=b[1]&15u;
    result.x=(uint16_t)(((b[2]&15u)<<8)|b[3]);
    result.y=(uint16_t)(((b[4]&15u)<<8)|b[5]);
    if (result.fingers>1 || (result.fingers && (result.x>=172 || result.y>=320))) return 0;
    *sample=result;
    return 1;
}

void watch_touch_cancel(watch_touch_session *t) { if (t) t->active=0; }

int watch_touch_apply(watch_state *s, watch_touch_session *t, const watch_touch_sample *p, uint32_t now) {
    unsigned dx,dy;
    if (!s || !t || !p) return 0;
    if (p->fingers>1 || (p->fingers && (p->x>=172 || p->y>=320))) { t->active=0; return 0; }
    if (p->fingers) {
        if (!t->active) {
            t->active=1; t->start_x=p->x; t->start_y=p->y;
            t->started_ms=now; t->max_dx=0; t->max_dy=0;
        }
        t->last_x=p->x; t->last_y=p->y;
        dx=distance(t->start_x,p->x); dy=distance(t->start_y,p->y);
        if (dx>t->max_dx) t->max_dx=(uint16_t)dx;
        if (dy>t->max_dy) t->max_dy=(uint16_t)dy;
        return 0;
    }
    if (!t->active) return 0;
    t->active=0;
    dx=distance(t->start_x,t->last_x); dy=distance(t->start_y,t->last_y);
    if (now-t->started_ms>2000u) return 0;
    if (dy>=24 && dy>dx) return watch_swipe(s,t->last_y>t->start_y?1:-1);
    if (dx>=24 && dx>dy) {
        if (t->last_x>t->start_x) { watch_open(s,WATCH_FACE); return 1; }
        if (s->page==WATCH_FACE) { watch_open(s,WATCH_NOTICES); return 1; }
        return 0;
    }
    if (t->max_dx<=8 && t->max_dy<=8 && now-t->started_ms<=600u)
        return watch_tap(s,172,320,t->start_x,t->start_y,now);
    return 0;
}
