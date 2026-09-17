#pragma once
#include "wire.h"
#include <zephyr/kernel.h>
struct capture_config {
    bool fd, active;
    uint32_t bitrate, data_bitrate;
    uint16_t sp, data_sp;
};
struct tx_event {
    uint32_t request, completed;
    int error;
    bool terminal;
};
extern struct k_msgq rx_queue, tx_events;
extern struct capture_config applied;
extern uint64_t boot_session;
int capture_init(void);
int capture_configure(const struct capture_config *cfg);
int capture_start(void);
void capture_stop(void);
void capture_lease(void);
int capture_tx(const struct w_frame *f, uint32_t interval, uint32_t count, uint32_t request);
void capture_cancel(void);
void capture_discard(unsigned n);
void capture_discard_tx(unsigned n);
size_t capture_status(char *buffer, size_t size);
int network_init(void);
int network_provision(const uint8_t *p, size_t n);
const char *network_mode(void);
int network_error(void);
size_t network_status(char *out, size_t size);
void server_run(void);
