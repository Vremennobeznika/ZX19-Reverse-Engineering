/* Original R19Z startup implementation, derived from exact-image observations.
 * Object-only bring-up stage. No flash transport; board/app callbacks must be
 * implemented before linking a device image. OTP here is a RAM shadow, not eFuse.
 */
#include <stdint.h>

#define REG32(a) (*(volatile uint32_t *)(uintptr_t)(a))
#define REG8(a) (*(volatile uint8_t *)(uintptr_t)(a))
extern uint8_t __r19z_data_load[], __r19z_data_start[], __r19z_data_end[];
extern uint8_t __r19z_bss_start[], __r19z_bss_end[];
extern void r19z_pre_main(void);
extern void r19z_app_main(void);
extern void r19z_watchdog_callback(uint32_t mode, uint32_t reason);

static const uint8_t expected_rom[16] = {
    0x1d,0x6a,0x69,0xf1,0x2f,0x38,0xea,0x11,
    0x82,0xa7,0x67,0x37,0x0a,0x3c,0xa3,0x2e
};

static int header_matches(uint32_t address, uint16_t id) {
    /* Only the documented mapped flash window; arithmetic cannot wrap. */
    if (address < 0x800000u || address > 0xffffe0u || (address & 3u)) return 0;
    if (REG8(address) != 9 || (REG32(address) & (1u << 23))) return 0;
    if (*(volatile uint16_t *)(uintptr_t)(address + 4) != id) return 0;
    for (unsigned i=0; i<16; ++i)
        if (REG8(address+12+i) != expected_rom[i]) return 0;
    return 1;
}

/* Called by the chip's existing ROM boot sequence, not a Cortex vector reset.
 * Return 1 when callbacks are installed; 0 leaves runtime untouched.
 */
__attribute__((section(".r19z.entry"), used))
int r19z_system_init(void) {
    int (*check_hci)(void) = (int (*)(void))(uintptr_t)0xd8a5;
    uint32_t (*active_bank)(void) = (uint32_t (*)(void))(uintptr_t)0x112d;
    int (*check_header)(uint32_t, uint16_t) =
        (int (*)(uint32_t, uint16_t))(uintptr_t)0xd8bd;
    if (check_hci() || !(REG8(0x2002dc) & 1u)) return 0;
    uint32_t bank = active_bank();
    if (bank < 0x800000u || bank > 0xfff000u || (bank & 0xfffu)) return 0;
    if (!check_header(bank, 0x2790)) return 0;
    uint32_t stack_address = REG32(bank + 0x1e0);
    uint32_t stack_size = REG32(bank + 0x1e4);
    if (stack_size < 1024 || stack_size > 0x800000u ||
        stack_address < 0x800000u || stack_address > 0x1000000u-stack_size ||
        !header_matches(stack_address, 0x279a)) return 0;
    uint32_t stack_entry = REG32(stack_address+28) & ~1u;
    if (stack_entry < stack_address+1024 || stack_entry >= stack_address+stack_size) return 0;

    for (uint8_t *p=__r19z_data_start; p<__r19z_data_end; ++p)
        *p=__r19z_data_load[p-__r19z_data_start];
    for (uint8_t *p=__r19z_bss_start; p<__r19z_bss_end; ++p) *p=0;

    REG32(0x200380)=0x208500;
    REG32(0x200384)=0x13f00;
    REG32(0x200388)=0x7d00;
    REG32(0x200cc0)=(uint32_t)(uintptr_t)r19z_pre_main;
    REG32(0x200cc4)=stack_entry | 1u;
    REG32(0x200cc8)=(uint32_t)(uintptr_t)r19z_app_main;
    REG32(0x200fb4)=(uint32_t)(uintptr_t)r19z_watchdog_callback;
    return 1;
}
