/* Host preview bridge only. Not part of an on-device image. */
#include "../src/watch_core.h"
#include "../src/watch_render.h"
#include "../src/watch_input.h"
#include "../src/watch_touch.h"
#define UI_EXPORT(name) __attribute__((export_name(#name)))

__attribute__((import_module("env"), import_name("fill")))
extern void host_fill(int x,int y,int w,int h,int color);
static watch_state state;
static watch_touch_session touch;
static char message[512];
static void fill(void *ctx,int x,int y,int w,int h,uint16_t color) {
    (void)ctx;host_fill(x,y,w,h,color);
}
UI_EXPORT(ui_init) void ui_init(unsigned now) { watch_init(&state,now);watch_touch_cancel(&touch); }
UI_EXPORT(ui_tick) void ui_tick(unsigned now,unsigned wall) { watch_tick(&state,now,wall); }
UI_EXPORT(ui_draw) void ui_draw(unsigned wall,unsigned day,unsigned month) {
    watch_canvas canvas={172,320,fill,0};
    watch_render(&state,&canvas,watch_take_dirty(&state),wall,day,month);
}
UI_EXPORT(ui_touch) void ui_touch(unsigned x,unsigned y,unsigned fingers,unsigned now) {
    watch_touch_sample sample={(uint16_t)x,(uint16_t)y,(uint8_t)fingers,0};
    watch_touch_apply(&state,&touch,&sample,now);
}
UI_EXPORT(ui_cancel) void ui_cancel(void) { watch_touch_cancel(&touch); }
UI_EXPORT(ui_button) void ui_button(unsigned held,unsigned now) { watch_button(&state,(int)held,now); }
UI_EXPORT(ui_home) void ui_home(void) { watch_open(&state,WATCH_FACE); }
UI_EXPORT(ui_next) void ui_next(int direction) { watch_swipe(&state,direction); }
UI_EXPORT(ui_page) unsigned ui_page(void) { return state.page; }
UI_EXPORT(ui_timer_ms) unsigned ui_timer_ms(void) { return state.timer_ms; }
UI_EXPORT(ui_notice_count) unsigned ui_notice_count(void) { return state.notice_count; }
UI_EXPORT(ui_alarm) unsigned ui_alarm(void) { return (unsigned)watch_take_alarm(&state); }
UI_EXPORT(ui_message_buffer) char *ui_message_buffer(void) { return message; }
UI_EXPORT(ui_notice) int ui_notice(unsigned length) {
    if (length>sizeof(message)) return 0;
    return watch_notice(&state,message,length);
}
