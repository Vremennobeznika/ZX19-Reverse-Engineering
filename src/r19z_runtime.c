/* R19Z 1.00.18 ROM ABI. No flash or radio commands in the display task. */
#include <stdbool.h>
#include "r19z_display_app.h"
#include "r19z_i2c.h"
#include "watch_touch.h"

static r19z_display_app display;
static void *task_handle;
static volatile uint32_t watchdog_reason;

static void display_task(void *argument) {
    (void)argument;
    uint64_t (*uptime)(void) = (uint64_t (*)(void))(uintptr_t)0x13047;
    void (*sleep_ms)(uint32_t) = (void (*)(uint32_t))(uintptr_t)0x13029;
    bool (*delete_task)(void *) = (bool (*)(void *))(uintptr_t)0x13353;
    r19z_clock_sample clock = {(uint32_t)uptime(), UINT32_MAX, 0, 0};
    int ready = r19z_display_start(&display, &clock);
    r19z_i2c_bus i2c = {4096, 0};
    watch_touch_bus touch = {&i2c, r19z_touch_i2c_read, 0};
    watch_touch_session gesture;
    watch_touch_cancel(&gesture);
    if (ready) {
        r19z_touch_setup();
        watch_touch_probe(&touch);
    }
    while (ready) {
        uint32_t wait = watch_deadline_ms(&display.watch, 1);
        if (touch.chip_id && wait > 32) wait = 32;
        if (wait > 60000) wait = 60000;
        sleep_ms(wait);
        clock.monotonic_ms = (uint32_t)uptime();
        if (touch.chip_id) {
            watch_touch_sample sample;
            if (watch_touch_read(&touch, &sample))
                watch_touch_apply(&display.watch, &gesture, &sample, clock.monotonic_ms);
            else {
                watch_touch_cancel(&gesture);
                if (i2c.fault) touch.chip_id = 0;
            }
        }
        ready = r19z_display_update(&display, &clock);
    }
    delete_task(task_handle);
}

void r19z_pre_main(void) {
    __asm__ volatile ("cpsid i" ::: "memory");
    volatile uint32_t *disable_irq = (volatile uint32_t *)0xe000e180u;
    *disable_irq = (1u << 22) | (1u << 23);
    if (*(volatile uint32_t *)0xe000ed08u != 0x200000u) {
        void (*init_vectors)(uint32_t) = (void (*)(uint32_t))(uintptr_t)0x4d39;
        init_vectors(0x200000u);
    }
    __asm__ volatile ("dsb\n isb" ::: "memory");
}

void r19z_app_main(void) {
    bool (*create_task)(void **, const char *, void (*)(void *), void *, uint16_t, uint16_t) =
        (bool (*)(void **, const char *, void (*)(void *), void *, uint16_t, uint16_t))(uintptr_t)0x1330d;
    bool (*start_scheduler)(void) = (bool (*)(void))(uintptr_t)0x130a1;
    *(volatile uint8_t *)0x20039bu |= 0x80u;
    if (create_task(&task_handle, "ZX19", display_task, 0, 2048, 1))
        start_scheduler();
}

void r19z_watchdog_callback(uint32_t mode, uint32_t reason) {
    (void)mode;
    watchdog_reason = reason;
}
