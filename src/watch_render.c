#include "watch_render.h"

/* Original 5x7 bitmap alphabet. Rows are five-bit masks, no external font. */
static const uint8_t digits[10][7] = {
 {14,17,19,21,25,17,14},{4,12,4,4,4,4,14},{14,17,1,2,4,8,31},
 {30,1,1,14,1,1,30},{2,6,10,18,31,2,2},{31,16,16,30,1,1,30},
 {14,16,16,30,17,17,14},{31,1,2,4,8,8,8},{14,17,17,14,17,17,14},
 {14,17,17,15,1,1,14}};
static const uint8_t latin[26][7] = {
 {14,17,17,31,17,17,17},{30,17,17,30,17,17,30},{15,16,16,16,16,16,15},
 {30,17,17,17,17,17,30},{31,16,16,30,16,16,31},{31,16,16,30,16,16,16},
 {15,16,16,19,17,17,15},{17,17,17,31,17,17,17},{14,4,4,4,4,4,14},
 {7,2,2,2,18,18,12},{17,18,20,24,20,18,17},{16,16,16,16,16,16,31},
 {17,27,21,21,17,17,17},{17,25,21,19,17,17,17},{14,17,17,17,17,17,14},
 {30,17,17,30,16,16,16},{14,17,17,17,21,18,13},{30,17,17,30,20,18,17},
 {15,16,16,14,1,1,30},{31,4,4,4,4,4,4},{17,17,17,17,17,17,14},
 {17,17,17,17,17,10,4},{17,17,17,21,21,27,17},{17,17,10,4,10,17,17},
 {17,17,10,4,4,4,4},{31,1,2,4,8,16,31}};
static const uint8_t russian[32][7] = {
 {14,17,17,31,17,17,17},{31,16,16,30,17,17,30},{30,17,17,30,17,17,30},
 {31,16,16,16,16,16,16},{6,10,10,10,10,31,17},{31,16,16,30,16,16,31},
 {21,21,14,4,14,21,21},{14,17,1,6,1,17,14},{17,17,19,21,25,17,17},
 {10,4,17,19,21,25,17},{17,18,20,24,20,18,17},{7,9,9,9,9,9,17},
 {17,27,21,21,17,17,17},{17,17,17,31,17,17,17},{14,17,17,17,17,17,14},
 {31,17,17,17,17,17,17},{30,17,17,30,16,16,16},{15,16,16,16,16,16,15},
 {31,4,4,4,4,4,4},{17,17,17,15,1,17,14},{4,14,21,21,14,4,4},
 {17,17,10,4,10,17,17},{17,17,17,17,17,31,1},{17,17,17,15,1,1,1},
 {21,21,21,21,21,21,31},{21,21,21,21,21,31,1},{24,8,8,14,9,9,14},
 {17,17,17,25,21,21,25},{16,16,16,30,17,17,30},{14,17,1,7,1,17,14},
 {18,21,21,29,21,21,18},{15,17,17,15,5,9,17}};
static const uint8_t colon[7]={0,4,4,0,4,4,0}, dot[7]={0,0,0,0,0,4,4};
static const uint8_t dash[7]={0,0,0,31,0,0,0}, blank[7]={0};
static const uint8_t exclamation[7]={4,4,4,4,4,0,4}, comma[7]={0,0,0,0,4,4,8};
static const uint8_t question[7]={14,17,1,2,4,0,4};
static const uint8_t plus[7]={0,4,4,31,4,4,0};
static const uint8_t unknown[7]={31,17,17,17,17,17,31};

typedef struct {
    int width, height;
    watch_fill_fn fill;
    void *context;
    int top, bottom;
} render_canvas;

static void rect(const render_canvas *c, int x, int y, int w, int h, uint16_t color) {
    if (x < 0) { w += x; x = 0; }
    if (y < 0) { h += y; y = 0; }
    if (x >= c->width || y >= c->height || w <= 0 || h <= 0) return;
    if (w > c->width-x) w = c->width-x;
    if (h > c->height-y) h = c->height-y;
    if (y < c->top) { h -= c->top-y; y=c->top; }
    if (y >= c->bottom || h <= 0) return;
    if (h > c->bottom-y) h=c->bottom-y;
    c->fill(c->context,x,y,w,h,color);
}
static const uint8_t *glyph(unsigned cp) {
    if (cp >= '0' && cp <= '9') return digits[cp-'0'];
    if (cp >= 'a' && cp <= 'z') cp -= 32;
    if (cp >= 'A' && cp <= 'Z') return latin[cp-'A'];
    if (cp >= 0x430 && cp <= 0x44f) cp -= 32;
    if (cp >= 0x410 && cp <= 0x42f) return russian[cp-0x410];
    if (cp == 0x401 || cp == 0x451) return russian[5];
    if (cp == ':') return colon;
    if (cp == '.') return dot;
    if (cp == '-') return dash;
    if (cp == '!') return exclamation;
    if (cp == ',') return comma;
    if (cp == '?') return question;
    if (cp == '+') return plus;
    if (cp == ' ') return blank;
    return unknown;
}
static unsigned next(const unsigned char **p) {
    unsigned cp = *(*p)++, more = 0;
    if (cp >= 0xc2 && cp <= 0xdf) { cp &= 31; more=1; }
    else if (cp >= 0xe0 && cp <= 0xef) { cp &= 15; more=2; }
    else if (cp >= 0xf0 && cp <= 0xf4) { cp &= 7; more=3; }
    while (more--) {
        if ((**p & 0xc0) != 0x80) return '?';
        cp=(cp<<6) | (*(*p)++ & 63);
    }
    return cp;
}
static void text(const render_canvas *c, int x, int y, const char *s, int scale, int wrap) {
    if (y >= c->bottom || (!wrap && y+7*scale <= c->top)) return;
    const unsigned char *p=(const unsigned char *)s;
    int origin=x;
    while (*p && y+7*scale <= c->height-4) {
        if (wrap && *p!=' ' && (p==(const unsigned char *)s || p[-1]==' ')) {
            const unsigned char *q=p;
            int count=0, available=(c->width-8-origin)/(6*scale);
            while (*q && *q!=' ' && count<=available) { next(&q); ++count; }
            if (count<=available && x+count*6*scale-scale>c->width-8) { x=origin; y+=9*scale; }
        }
        if (wrap && *p==' ' && x==origin) { ++p; continue; }
        unsigned cp=next(&p);
        int row,col;
        if (x+5*scale > c->width-8) {
            if (!wrap) return;
            x=origin; y+=9*scale;
            if (y+7*scale > c->height-4) return;
        }
        if (y >= c->bottom) return;
        if (y+7*scale <= c->top) { x+=6*scale; continue; }
        const uint8_t *g=glyph(cp);
        for (row=0;row<7;++row) {
            if (y+(row+1)*scale <= c->top) continue;
            if (y+row*scale >= c->bottom) break;
            col=0;
            while (col<5) {
                int start;
                if (!(g[row] & (16u>>col))) { ++col; continue; }
                start=col++;
                while (col<5 && (g[row] & (16u>>col))) ++col;
                rect(c,x+start*scale,y+row*scale,(col-start)*scale,scale,0xffff);
            }
        }
        x+=6*scale;
    }
}
static void two(char *dest, unsigned n) { n%=100; dest[0]=(char)('0'+n/10); dest[1]=(char)('0'+n%10); }
static void duration(char *out, uint32_t ms, int round_up) {
    uint32_t sec=ms/1000u + ((round_up && ms%1000u)?1u:0u);
    two(out,sec/3600u); out[2]=':'; two(out+3,sec/60u%60u); out[5]=':'; two(out+6,sec%60u); out[8]=0;
}
static void card(const render_canvas *c, int y, const char *label, int selected) {
    if (y >= c->bottom || y+44 <= c->top) return;
    uint16_t border=selected?0xffff:0x7bef;
    rect(c,8,y,c->width-16,1,border); rect(c,8,y+43,c->width-16,1,border);
    rect(c,8,y,1,44,border); rect(c,c->width-9,y,1,44,border);
    text(c,16,y+15,label,c->width<160?1:2,0);
}

static void render(const watch_state *s, const render_canvas *c, unsigned dirty,
                  unsigned local_seconds, unsigned day, unsigned month) {
    char value[9];
    if (!s || !c || !c->fill || !dirty || c->width<128 || c->height<200 || c->width>1024 || c->height>1024) return;
    if (dirty==WATCH_FULL) {
        static const char * const titles[]={"ЧАСЫ","МЕНЮ","ТАЙМЕР","СЕКУНДОМЕР","СООБЩЕНИЯ"};
        rect(c,0,0,c->width,c->height,0);
        text(c,10,14,titles[s->page<=WATCH_NOTICES?s->page:0],c->width<160?1:2,0);
        rect(c,8,40,c->width-16,1,0x7bef);
        if (s->page==WATCH_MENU) {
            card(c,58,"ТАЙМЕР",s->selected==0);
            card(c,112,"СЕКУНДОМЕР",s->selected==1);
            card(c,166,"УВЕДОМЛЕНИЯ",s->selected==2);
        } else if (s->page==WATCH_TIMER || s->page==WATCH_STOPWATCH) {
            int running=s->page==WATCH_TIMER?s->timer_running:s->stopwatch_running;
            card(c,c->height-74,running?"ПАУЗА":"СТАРТ",1);
            if (s->page==WATCH_TIMER && !running) {
                if (c->height>=260) {
                    int y=c->height-140,w=(c->width-24)/2,i;
                    text(c,12,y-15,"ВРЕМЯ",1,0);
                    for (i=0;i<2;++i) {
                        int x=8+i*(w+8);
                        rect(c,x,y,w,1,0x7bef);rect(c,x,y+43,w,1,0x7bef);
                        rect(c,x,y,1,44,0x7bef);rect(c,x+w-1,y,1,44,0x7bef);
                        text(c,x+12,y+18,i?"+1 МИН":"-1 МИН",1,0);
                    }
                } else text(c,12,115,"СВАЙП: ВРЕМЯ",1,0);
            }
            if (s->page==WATCH_STOPWATCH) text(c,12,c->height-18,"УДЕРЖИ: СБРОС",1,0);
        } else if (s->page==WATCH_NOTICES) {
            if (!s->notice_count) text(c,12,72,"НЕТ СООБЩЕНИЙ",2,1);
            else {
                unsigned i=(s->notice_head+3u-(s->selected% s->notice_count))%4u;
                text(c,12,60,s->notices[i],2,1);
            }
        }
    }
    if (s->page==WATCH_FACE) {
        int scale=(c->width-16)/30;
        if (scale>5) scale=5;
        two(value,local_seconds/3600u%24u); value[2]=':'; two(value+3,local_seconds/60u%60u); value[5]=0;
        if (dirty!=WATCH_FULL) {
            rect(c,(c->width-29*scale)/2,82,29*scale,7*scale,0);
            rect(c,(c->width-60)/2,139,60,14,0);
        }
        text(c,(c->width-30*scale+scale)/2,82,value,scale,0);
        two(value,day); value[2]='.'; two(value+3,month); value[5]=0;
        text(c,(c->width-60)/2,139,value,2,0);
        if (dirty==WATCH_FULL) card(c,c->height-74,"МЕНЮ",1);
    } else if (s->page==WATCH_TIMER || s->page==WATCH_STOPWATCH) {
        int scale=c->width>=160?3:2;
        duration(value,s->page==WATCH_TIMER?s->timer_ms:s->stopwatch_ms,s->page==WATCH_TIMER);
        if (dirty!=WATCH_FULL) rect(c,(c->width-47*scale)/2,83,47*scale,7*scale,0);
        text(c,(c->width-48*scale+scale)/2,83,value,scale,0);
    }
}

void watch_render_region(const watch_state *s, const watch_canvas *c, unsigned dirty,
                         unsigned local_seconds, unsigned day, unsigned month,
                         int top, int bottom) {
    if (!c || top < 0 || bottom <= top || bottom > c->height) return;
    render_canvas clipped = {c->width, c->height, c->fill, c->context, top, bottom};
    render(s, &clipped, dirty, local_seconds, day, month);
}

void watch_render(const watch_state *s, const watch_canvas *c, unsigned dirty,
                  unsigned local_seconds, unsigned day, unsigned month) {
    if (!c) return;
    watch_render_region(s, c, dirty, local_seconds, day, month, 0, c->height);
}
