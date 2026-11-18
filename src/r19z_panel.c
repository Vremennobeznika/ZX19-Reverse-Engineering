#include "r19z_panel.h"
#include "r19z_pins.h"

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

void r19z_configure_pad(unsigned index, unsigned low_bits, unsigned flags) {
    uint8_t (*read_pad)(unsigned) = (uint8_t (*)(unsigned))(uintptr_t)0x2d5b1;
    void (*write_pad)(unsigned, unsigned) = (void (*)(unsigned, unsigned))(uintptr_t)0x2d5f3;
    write_pad(index, (read_pad(index) & 0xf0u) | low_bits);
    write_pad(index+1, (read_pad(index+1) & ~3u) | flags);
}

static int reset_mode(void *context, unsigned mode) {
    (void)context;
    r19z_configure_pad(0xc4, mode ? 0x0eu : 0x07u, 1);
    return 1;
}

int r19z_panel_start(watch_lcd *lcd, watch_lcd_delay_fn delay) {
    if (!lcd || lcd->fault || !delay) return 0;
    lcd->command = command;
    lcd->data = data;
    return watch_lcd_start_r19z_first(lcd, reset_mode, delay);
}

/* The vendor runtime publishes platform_delay_ms in this RAM slot. */
static uintptr_t delay_entry(void) {
    uintptr_t entry = *(volatile uint32_t *)0x2004f4u;
    return (entry & 1u) && entry != UINT32_MAX && entry != 1u ? entry : 0;
}

static int platform_delay(void *context, unsigned ms) {
    (void)context;
    uintptr_t entry = delay_entry();
    if (!entry) return 0;
    ((void (*)(unsigned))entry)(ms);
    return 1;
}

#define REG32(address) (*(volatile uint32_t *)(uintptr_t)(address))

void r19z_select_pin(unsigned pin, unsigned function) {
    unsigned shift = (pin & 3u) * 8u;
    volatile uint32_t *reg = &REG32(0x40000280u + (pin / 4u) * 4u);
    *reg = (*reg & ~(0xffu << shift)) | (function << shift);
}

static void prepare_display_bus(void) {
    /* 0x83228a..0x832478 in R19Z_1.00.18. Each pair is a pin number
     * and its first AON byte from the stock pad map. */
    static const uint8_t pins[][2] = {
        {29,0x90}, {1,0xe2}, {2,0xe4}, {4,0xe8}, {32,0xa6}, {33,0xa8},
        {34,0xaa}, {35,0xac}, {27,0x8c}, {28,0x8e}, {5,0xa0}, {26,0x8a}
    };
    REG32(0x40000218) &= ~0x02000000u;
    REG32(0x40000238) &= ~0x30000000u;
    REG32(0x40000218) |= 0x02000000u;
    REG32(0x40000238) |= 0x30000000u;
    REG32(0x400002a8) &= ~0x30000000u;
    REG32(0x400002a8) |= 0x20000000u;
    uint32_t hz = REG32(0x200100);
    unsigned timing = 0x30;
    if (hz == 90000000 || hz == 100000000) timing = 0x40;
    if (hz == 40000000) timing = 0x10;
    REG32(0x40024808) = 0xfea;
    REG32(0x40024800) = 0x94809u | timing;
    REG32(0x40024804) = 0x40;
    DISPLAY_CONTROL = 0x40000100u;
    REG32(0x40024810) = 0x42;
    for (unsigned i = 0; i < sizeof(pins)/sizeof(pins[0]); ++i)
        r19z_configure_pad(pins[i][1], 2, 3);
    for (unsigned i = 0; i < sizeof(pins)/sizeof(pins[0]); ++i)
        r19z_select_pin(pins[i][0], 0);
    r19z_configure_pad(0xce, 2, 3);
    r19z_select_pin(23, 0x11);
}

int r19z_panel_start_platform(watch_lcd *lcd) {
    if (!lcd || lcd->fault || !delay_entry()) return 0;
    prepare_display_bus();
    /* Board enable H_0 and settling delay at 0x832598..0x8325b6. */
    r19z_configure_pad(0xd0, 2, 1);
    if (!platform_delay(lcd->context, 50)) { lcd->fault = 1; return 0; }
    return r19z_panel_start(lcd, platform_delay);
}
