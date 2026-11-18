/* Test-only callbacks, deliberately not board implementations. */
#include <stdint.h>
volatile uint32_t boot_fixture_data = 0x1234abcd;
volatile uint32_t boot_fixture_bss;
void r19z_pre_main(void) { }
void r19z_app_main(void) { boot_fixture_bss=boot_fixture_data; }
void r19z_watchdog_callback(uint32_t mode, uint32_t reason) { (void)mode; (void)reason; }
