#include "r19z_panel.h"

#define DISPLAY_CONTROL (*(volatile uint32_t *)0x40024814u)
#define DISPLAY_BYTE (*(volatile uint32_t *)0x40024838u)
enum { DATA_MODE = 0x200, START = 0x400, COMMAND_PULSE = 0x100 };

static int wait_complete(void) {
    for (unsigned remaining = 4096; remaining; --remaining)
        if (!(DISPLAY_CONTROL & START)) return 1;
    return 0;
}

static int command(void *context, uint8_t value) {
    (void)context;
    DISPLAY_CONTROL |= COMMAND_PULSE;
    __asm__ volatile ("nop\n nop\n nop\n nop" ::: "memory");
    DISPLAY_CONTROL &= ~COMMAND_PULSE;
    DISPLAY_BYTE = value;
    DISPLAY_CONTROL &= ~DATA_MODE;
    DISPLAY_CONTROL |= START;
    return wait_complete();
}

static int data(void *context, const uint8_t *bytes, size_t length) {
    (void)context;
    for (size_t i = 0; i < length; ++i) {
        DISPLAY_BYTE = bytes[i];
        DISPLAY_CONTROL |= DATA_MODE | START;
        if (!wait_complete()) return 0;
    }
    return 1;
}

static int reset_mode(void *context, unsigned mode) {
    (void)context;
    /* R19Z ROM AON accessors and the P2_2 table entry in image 1.00.18. */
    uint8_t (*read_pad)(unsigned) = (uint8_t (*)(unsigned))(uintptr_t)0x2d5b1;
    void (*write_pad)(unsigned, unsigned) = (void (*)(unsigned, unsigned))(uintptr_t)0x2d5f3;
    unsigned config = read_pad(0xc4);
    write_pad(0xc4, (config & 0xf0u) | (mode ? 0x0eu : 0x07u));
    config = read_pad(0xc5);
    write_pad(0xc5, (config & ~3u) | 1u);
    return 1;
}

int r19z_panel_start(watch_lcd *lcd, watch_lcd_delay_fn delay) {
    if (!lcd || lcd->fault || !delay) return 0;
    lcd->command = command;
    lcd->data = data;
    return watch_lcd_start_r19z_first(lcd, reset_mode, delay);
}
