/* Original bounded MMIO transport for the observed R19Z I2C1 controller.
 * Register layout cross-checked with RTL8762D rtl876x.h/rtl876x_i2c.h.
 */
#include "r19z_i2c.h"
#define IC(offset) (*(volatile uint32_t *)(uintptr_t)(0x40015400u+(offset)))
#define COMMAND 0x10
#define RAW_IRQ 0x34
#define CLEAR_IRQ 0x40
#define CLEAR_STOP 0x60
#define ENABLE 0x6c
#define STATUS 0x70
#define ABORT_SOURCE 0x80
#define ERROR_FLAGS ((1u<<6)|(1u<<3)|(1u<<1)|(1u<<0))

static int wait_for(uint32_t offset, uint32_t mask, uint32_t value, uint32_t *budget) {
    while (*budget) {
        --*budget;
        if (IC(RAW_IRQ) & ERROR_FLAGS) return 0;
        if ((IC(offset) & mask)==value) return 1;
    }
    return 0;
}

int r19z_touch_i2c_read(void *context, uint8_t address, uint8_t reg,
                        uint8_t *output, size_t size) {
    r19z_i2c_bus *bus=context;
    uint8_t result[6];
    if (!bus || bus->fault || !bus->poll_budget || !output || !size || size>6 || address!=0x15)
        return 0;
    uint32_t budget=bus->poll_budget;
    if (budget>4096u) budget=4096u;
    /* Do not reconfigure/interrupt an active transfer or a different target. */
    if (!(IC(ENABLE)&1u) || (IC(0x04)&0x3ffu)!=address ||
        (IC(0x00)&0x61u)!=0x61u || (IC(STATUS)&1u)) return 0;
    if (IC(STATUS)&8u) { bus->fault=1; return 0; } /* stale RX bytes */
    (void)IC(CLEAR_IRQ);
    if (!wait_for(STATUS,2,2,&budget)) goto failed;
    IC(COMMAND)=reg;
    for (size_t i=0;i<size;++i) {
        if (!wait_for(STATUS,2,2,&budget)) goto failed;
        /* Direction change generates RESTART in the configured controller. */
        IC(COMMAND)=0x100u | (i+1==size ? 0x200u : 0u);
        if (!wait_for(STATUS,8,8,&budget)) goto failed;
        result[i]=(uint8_t)IC(COMMAND);
    }
    if (!wait_for(RAW_IRQ,0x200,0x200,&budget)) goto failed;
    (void)IC(CLEAR_STOP);
    if (!wait_for(STATUS,1,0,&budget)) goto failed;
    for (size_t i=0;i<size;++i) output[i]=result[i];
    return 1;
failed:
    /* Our transfer failed: stop controller and demand explicit reinitialization. */
    (void)IC(ABORT_SOURCE);
    IC(ENABLE)=0;
    (void)IC(CLEAR_IRQ);
    bus->fault=1;
    return 0;
}
