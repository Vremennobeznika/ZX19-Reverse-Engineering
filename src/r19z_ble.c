#include "profile_server.h"
#include "gap_adv.h"
#include "gap_bond_le.h"
#include "gap_msg.h"
#include "app_msg.h"
#include "os_msg.h"
#include <stddef.h>

extern int r19z_receive_time(const uint8_t *,size_t);
static void *events, *messages;
static T_SERVER_ID time_service;

static T_APP_RESULT gap_event(uint8_t type,void *value) {
    (void)type;
    (void)value;
    return APP_RESULT_SUCCESS;
}
/* QC command service and write characteristic, little-endian on ATT. */
static const uint8_t service_uuid[] = {
    0x9e,0xca,0xdc,0x24,0x0e,0xe5,0xa9,0xe0,0x93,0xf3,0xa3,0xb5,0xf0,0xff,0x40,0x6e
};
static T_ATTRIB_APPL attributes[] = {
    {ATTRIB_FLAG_LE,{0x00,0x28},16,(void *)service_uuid,GATT_PERM_READ},
    {ATTRIB_FLAG_VALUE_INCL,{0x03,0x28,GATT_CHAR_PROP_WRITE | GATT_CHAR_PROP_WRITE_NO_RSP},
     1,NULL,GATT_PERM_READ},
    {ATTRIB_FLAG_UUID_128BIT | ATTRIB_FLAG_VALUE_APPL,
     {0x9e,0xca,0xdc,0x24,0x0e,0xe5,0xa9,0xe0,0x93,0xf3,0xa3,0xb5,0x02,0x00,0x40,0x6e},
     0,NULL,GATT_PERM_WRITE_ENCRYPTED_REQ}
};

static T_APP_RESULT write_time(uint8_t conn, T_SERVER_ID service, uint16_t index,
                               T_WRITE_TYPE type, uint16_t length, uint8_t *value,
                               P_FUN_WRITE_IND_POST_PROC *post) {
    (void)conn;
    (void)type;
    (void)post;
    if (service != time_service || index != 2) return APP_RESULT_ATTR_NOT_FOUND;
    if (length != 16) return APP_RESULT_INVALID_VALUE_SIZE;
    return r19z_receive_time(value,length) ? APP_RESULT_SUCCESS : APP_RESULT_REJECT;
}

bool r19z_ble_init(void) {
    uintptr_t dispatch = *(volatile uint32_t *)0x202a60u;
    if (!(dispatch & 1u) || dispatch == UINT32_MAX || dispatch == 1) return false;
    if (!le_gap_init(1)) return false;
    gap_lib_init();
    le_register_app_cb(gap_event);
    static uint8_t name[] = "ZX19 Libre";
    static uint8_t adv[] = {2,1,6,11,9,'Z','X','1','9',' ','L','i','b','r','e'};
    if (le_set_gap_param(GAP_PARAM_DEVICE_NAME,sizeof(name)-1,name) != GAP_CAUSE_SUCCESS ||
        le_adv_set_param(GAP_PARAM_ADV_DATA,sizeof(adv),adv) != GAP_CAUSE_SUCCESS) return false;
    server_init(1);
    const T_FUN_GATT_SERVICE_CBS callbacks = {NULL,write_time,NULL};
    return server_add_service(&time_service,(uint8_t *)attributes,sizeof(attributes),callbacks);
}

void r19z_ble_task(void *unused) {
    (void)unused;
    bool started = false;
    bool running = os_msg_queue_create(&messages,16,sizeof(T_IO_MSG)) &&
                   os_msg_queue_create(&events,32,sizeof(uint8_t)) &&
                   gap_start_bt_stack(events,messages,16);
    if (running) {
        for (;;) {
            uint8_t event;
            if (!os_msg_recv(events,&event,UINT32_MAX)) break;
            if (event != EVENT_IO_TO_APP) { gap_handle_msg(event); continue; }
            T_IO_MSG io;
            if (!os_msg_recv(messages,&io,0) || io.type != IO_MSG_TYPE_BT_STATUS) continue;
            T_LE_GAP_MSG_DATA status;
            _Static_assert(sizeof(status) <= sizeof(io.u), "Unexpected GAP event ABI");
            __builtin_memcpy(&status,&io.u,sizeof(status));
            if (io.subtype == GAP_MSG_LE_DEV_STATE_CHANGE && !started &&
                status.gap_dev_state_change.new_state.gap_init_state == GAP_INIT_STATE_STACK_READY)
                started = le_adv_start() == GAP_CAUSE_SUCCESS;
            else if (io.subtype == GAP_MSG_LE_CONN_STATE_CHANGE &&
                     status.gap_conn_state_change.new_state == GAP_CONN_STATE_DISCONNECTED)
                started = le_adv_start() == GAP_CAUSE_SUCCESS;
            else if (io.subtype == GAP_MSG_LE_BOND_JUST_WORK)
                le_bond_just_work_confirm(status.gap_bond_just_work_conf.conn_id,GAP_CFM_CAUSE_ACCEPT);
        }
    } else {
        if (events) os_msg_queue_delete(events);
        if (messages) os_msg_queue_delete(messages);
    }
    /* Once registered, the stack may retain its queues until reset. */
    ((bool (*)(void *))(uintptr_t)0x13353)(NULL);
}
