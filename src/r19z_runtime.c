/* R19Z 1.00.18 ROM ABI. No flash or radio commands in the display task. */
#include <stdbool.h>
#include "r19z_display_app.h"
#include "r19z_i2c.h"
#include "watch_touch.h"
#include "r19z_calendar.h"

static r19z_display_app display;
static void *task_handle;
static void *ble_task_handle;
static bool radio_first;
static volatile bool radio_advertising;
/* Retained across warm resets only when the ROM preserves this SRAM. */
static volatile struct { uint32_t count, check; } boots __attribute__((section(".noinit")));
#define BOOT_COOKIE 0x9b142f81u
extern bool r19z_update_active(void);
void r19z_radio_available(void) { radio_advertising = true; }
extern bool r19z_ble_init(void);
extern void r19z_ble_task(void *);
static volatile uint32_t watchdog_reason;
static r19z_calendar calendar;

static uint32_t lock_clock(void) {
    uint32_t mask;
    __asm__ volatile ("mrs %0, primask\n cpsid i" : "=r"(mask) :: "memory");
    return mask;
}

static void unlock_clock(uint32_t mask) {
    __asm__ volatile ("msr primask, %0" :: "r"(mask) : "memory");
}

/* Entry for a time write on the QC command service. */
int r19z_receive_time(const uint8_t *data, size_t length) {
    uint64_t (*uptime)(void) = (uint64_t (*)(void))(uintptr_t)0x13047;
    uint32_t mask = lock_clock();
    int accepted = r19z_calendar_accept(&calendar, data, length, (uint32_t)uptime());
    unlock_clock(mask);
    return accepted;
}

static void sample_clock(r19z_clock_sample *sample) {
    uint64_t (*uptime)(void) = (uint64_t (*)(void))(uintptr_t)0x13047;
    uint32_t mask = lock_clock();
    r19z_calendar_sample(&calendar, (uint32_t)uptime(), sample);
    unlock_clock(mask);
}

static void display_task(void *argument) {
    (void)argument;
    void (*sleep_ms)(uint32_t) = (void (*)(uint32_t))(uintptr_t)0x13029;
    bool (*delete_task)(void *) = (bool (*)(void *))(uintptr_t)0x13353;
    r19z_clock_sample clock;
    unsigned attempts=1;
    if ((boots.count ^ boots.check)==BOOT_COOKIE && boots.count<=3)
        attempts=boots.count<3 ? boots.count+1 : 3;
    boots.count=attempts;
    boots.check=BOOT_COOKIE ^ attempts;
    if (radio_first) {
        for (unsigned i=0;i<50 && !radio_advertising;i++) sleep_ms(100);
        if (radio_advertising) sleep_ms(attempts>=3 ? 15000 : 3000);
        while (r19z_update_active()) sleep_ms(500);
    }
    sample_clock(&clock);
    int ready = r19z_display_start(&display, &clock);
    uint32_t started_at=clock.monotonic_ms;
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
        while (r19z_update_active()) sleep_ms(500);
        sample_clock(&clock);
        if (boots.count && clock.monotonic_ms-started_at >= 60000u) {
            boots.count=0;
            boots.check=BOOT_COOKIE;
        }
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
    if (r19z_ble_init())
        radio_first = create_task(&ble_task_handle, "ZX19 BLE", r19z_ble_task, 0, 2560, 2);
    bool display_created = create_task(&task_handle, "ZX19", display_task, 0, 2048, 1);
    if (radio_first || display_created)
        start_scheduler();
}

void r19z_watchdog_callback(uint32_t mode, uint32_t reason) {
    (void)mode;
    watchdog_reason = reason;
}
