/* App-only OTA into the RTL8762D ROM-reported single-bank temporary area. */
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "r19z_owner.h"

typedef struct { uint32_t state[8]; uint64_t count; uint8_t buf[64]; } sha_ctx;
extern void SHA256_Init(sha_ctx *);
extern void SHA256_Update(sha_ctx *,const void *,size_t);
extern void SHA256_Final(sha_ctx *,uint8_t *);
extern uint32_t flash_get_bank_addr(int), flash_get_bank_size(int);
extern bool is_ota_support_bank_switch(void);
extern bool flash_sw_protect_unlock_by_addr_locked(uint32_t,uint8_t *);
extern bool flash_set_block_protect_locked(uint8_t), flash_erase_locked(int,uint32_t);
extern bool flash_write_locked(uint32_t,uint32_t,uint8_t *);
extern bool flash_read_locked(uint32_t,uint32_t,uint8_t *);
extern bool check_image_chksum(void *);
extern void WDG_SystemReset(int,int);

static const uint8_t uuid[16]={0x1d,0x6a,0x69,0xf1,0x2f,0x38,0xea,0x11,0x82,0xa7,0x67,0x37,0x0a,0x3c,0xa3,0x2e};
static const uint8_t owner_hash[32]=R19Z_OWNER_HASH;
static bool unlocked, committed;
static volatile bool receiving;
static uint32_t base,total,offset,used;
static uint8_t page[256];

static uint32_t word(const uint8_t *p) {
    return p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;
}
static bool same(const uint8_t *a,const uint8_t *b,size_t n) {
    unsigned diff=0;
    for(size_t i=0;i<n;i++) diff |= a[i]^b[i];
    return diff==0;
}
bool r19z_update_active(void) { return receiving || committed; }
void r19z_update_disconnect(void) {
    unlocked=false;
    receiving=false;
    if(committed) WDG_SystemReset(3,0xd4);
}
static bool begin(uint32_t n) {
    if(!unlocked || is_ota_support_bank_switch() || n<1024 || n>347972 || (n&3)) return false;
    uint32_t tmp=flash_get_bank_addr(4), capacity=flash_get_bank_size(4);
    uint32_t active=flash_get_bank_addr(2), active_size=flash_get_bank_size(2);
    uint32_t rounded=(n+4095u)&~4095u;
    if(tmp<0x800000 || tmp>=0x1000000 || (tmp&4095) || rounded>capacity ||
       capacity>0x1000000-tmp || active<0x800000 || active>0x82c000 ||
       active_size>0x1000000-active || active+active_size<0x880f44 ||
       (tmp<active+active_size && active<tmp+capacity)) return false;
    base=tmp; total=n; offset=used=0; receiving=true;
    return true;
}
static bool store_page(void) {
    if(!offset) {
        if(used<44 || word(page)!=0x09810009 || word(page+4)!=0x2793 ||
           word(page+8)!=total-1024 || !same(page+12,uuid,16) ||
           word(page+28)!=0x82c400 || word(page+32)!=0x82c400 ||
           word(page+36)!=0 || word(page+40)!=0x82c000) return false;
        page[2]|=0x80; /* Keep incomplete image in the SDK not-ready state. */
    }
    uint32_t address=base+offset;
    uint8_t old=0xff,readback[256];
    if(!flash_sw_protect_unlock_by_addr_locked(address,&old)) return false;
    bool ok=((offset&4095)!=0 || flash_erase_locked(2,address)) &&
            flash_write_locked(address,used,page);
    if(old!=0xff && !flash_set_block_protect_locked(old)) ok=false;
    if(!ok || !flash_read_locked(address,used,readback) || !same(page,readback,used)) return false;
    offset+=used; used=0;
    return true;
}
bool r19z_update_packet(const uint8_t *p,size_t n) {
    if(!p || !n || committed) return false;
    switch(p[0]) {
    case 1: {
        if(n!=17 || receiving) return false;
        uint8_t digest[32];
        sha_ctx ctx;
        SHA256_Init(&ctx); SHA256_Update(&ctx,p+1,16); SHA256_Final(&ctx,digest);
        unlocked=same(digest,owner_hash,32);
        return unlocked;
    }
    case 2: return n==5 && !receiving && begin(word(p+1));
    case 3:
        if(!receiving || n<=5 || word(p+1)!=offset+used || n-5>total-offset-used) return false;
        for(size_t i=5;i<n;i++) {
            page[used++]=p[i];
            if((used==sizeof(page) || offset+used==total) && !store_page()) {
                receiving=false; unlocked=false; return false;
            }
        }
        return true;
    case 4: {
        if(n!=1 || !receiving || offset!=total || used) return false;
        receiving=false; unlocked=false;
        uint32_t addr=base|0x4000000u;
        if(!check_image_chksum((void *)(uintptr_t)addr)) return false;
        uint8_t ctrl[4],old=0xff;
        if(!flash_read_locked(base,4,ctrl) || word(ctrl)!=0x09810009u ||
           !flash_sw_protect_unlock_by_addr_locked(base,&old)) return false;
        ctrl[2]&=0x7f;
        bool ok=flash_write_locked(base,4,ctrl);
        if(old!=0xff && !flash_set_block_protect_locked(old)) ok=false;
        uint8_t verified[4];
        committed=ok && flash_read_locked(base,4,verified) && same(ctrl,verified,4);
        return committed;
    }
    default: return false;
    }
}
