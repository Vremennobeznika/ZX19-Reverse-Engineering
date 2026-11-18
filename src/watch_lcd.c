#include "watch_lcd.h"

int watch_lcd_start_r19z_first(watch_lcd *lcd, watch_lcd_reset_mode_fn reset_mode,
                               watch_lcd_delay_fn delay) {
    if (!lcd || lcd->fault || !lcd->command || !lcd->data || !reset_mode || !delay) return 0;
    /* R19Z routine 0x83b066 uses pad 0x12 before the first panel init. */
    static const uint8_t wait_ms[] = {5, 20, 120};
    for (unsigned step = 0; step < sizeof(wait_ms); ++step) {
        if (!reset_mode(lcd->context, step == 1) || !delay(lcd->context, wait_ms[step])) {
            lcd->fault = 1;
            return 0;
        }
    }
    return watch_lcd_init_r19z_first(lcd, delay);
}

int watch_lcd_init_r19z_first(watch_lcd *lcd, watch_lcd_delay_fn delay) {
    /* Each record is command, payload length, payload. Stored in flash. */
    static const uint8_t sequence[] = {
        0x36,1,0, 0x3a,1,5, 0xb2,5,28,28,0,51,51,
        0xb7,1,53, 0xbb,1,53, 0xc0,1,44, 0xc2,1,1,
        0xc3,1,19, 0xc4,1,21, 0xd0,2,164,161, 0xd6,1,161,
        0xe0,14,240,0,4,4,4,5,41,51,62,56,18,18,40,48,
        0xe1,14,240,7,10,13,11,7,40,51,62,54,20,20,41,50,
        0x2a,4,0,34,0,205, 0x2b,4,0,0,1,63, 0xc6,1,27,
        0x35,1,0, 0x44,2,0,240, 0x21,0, 0x29,0, 0x2c,0
    };
    if (!lcd || lcd->fault || !lcd->command || !lcd->data || !delay) return 0;
    if (!lcd->command(lcd->context, 0x11) || !delay(lcd->context, 120)) goto fail;
    for (size_t offset = 0; offset < sizeof(sequence); ) {
        uint8_t command = sequence[offset++];
        uint8_t length = sequence[offset++];
        if (!lcd->command(lcd->context, command) ||
            (length && !lcd->data(lcd->context, sequence + offset, length))) goto fail;
        offset += length;
    }
    return 1;
fail:
    lcd->fault = 1;
    return 0;
}

int watch_lcd_fill(watch_lcd *lcd, int x, int y, int w, int h, uint16_t color) {
    uint8_t window[4], pixels[64];
    uint32_t count;
    unsigned i;
    int end;
    if (!lcd || !lcd->command || !lcd->data || lcd->fault) return 0;
    if (w<=0 || h<=0 || x>=172 || y>=320) return 1;
    /* Subtraction avoids signed x+width overflow for untrusted rectangle sizes. */
    if (x<0) { if (x<=-w) return 1; w+=x; x=0; }
    if (y<0) { if (y<=-h) return 1; h+=y; y=0; }
    if (w>172-x) w=172-x;
    if (h>320-y) h=320-y;
    end=x+w-1+34; x+=34;
    window[0]=(uint8_t)(x>>8); window[1]=(uint8_t)x;
    window[2]=(uint8_t)(end>>8); window[3]=(uint8_t)end;
    if (!lcd->command(lcd->context,0x2a) || !lcd->data(lcd->context,window,4)) goto fail;
    end=y+h-1;
    window[0]=(uint8_t)(y>>8); window[1]=(uint8_t)y;
    window[2]=(uint8_t)(end>>8); window[3]=(uint8_t)end;
    if (!lcd->command(lcd->context,0x2b) || !lcd->data(lcd->context,window,4) ||
        !lcd->command(lcd->context,0x2c)) goto fail;
    for (i=0;i<32;++i) { pixels[i*2]=(uint8_t)(color>>8); pixels[i*2+1]=(uint8_t)color; }
    count=(uint32_t)w*(uint32_t)h;
    while (count) {
        unsigned chunk=count>32?32:(unsigned)count;
        if (!lcd->data(lcd->context,pixels,chunk*2u)) goto fail;
        count-=chunk;
    }
    return 1;
fail:
    lcd->fault=1;
    return 0;
}

void watch_lcd_canvas_fill(void *context, int x, int y, int w, int h, uint16_t color) {
    (void)watch_lcd_fill((watch_lcd *)context,x,y,w,h,color);
}
