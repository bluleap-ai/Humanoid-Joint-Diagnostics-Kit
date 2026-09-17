#pragma once
#include <stdbool.h>
#include <stdint.h>
#define DT_ALIAS(x) 0
#define DEVICE_DT_GET(x) (&fake_device)
struct device {
    int unused;
};
static struct device fake_device;
static inline bool device_is_ready(const struct device *d) {
    (void)d;
    return true;
}
#define CAN_FRAME_IDE 1
#define CAN_FRAME_FDF 2
#define CAN_FRAME_BRS 4
#define CAN_FRAME_ESI 8
#define CAN_FRAME_RTR 16
#define CAN_FILTER_IDE 1
#define CAN_MODE_LISTENONLY 1
#define CAN_MODE_FD 2
#define CAN_MODE_ONE_SHOT 8
#define CAN_MODE_MANUAL_RECOVERY 4
struct can_frame {
    uint32_t id;
    uint8_t flags, dlc;
    uint8_t data[64];
};
struct can_filter {
    uint32_t id, mask;
    uint8_t flags;
};
struct can_timing {
    uint16_t prop_seg, phase_seg1, phase_seg2, prescaler;
};
enum can_state { CAN_STATE_ERROR_ACTIVE };
struct can_bus_err_cnt {
    unsigned tx_err_cnt, rx_err_cnt;
};
static int fake_mode, fake_sends, fake_stops;
static void (*fake_done)(const struct device *, int, void *);
static inline int can_stop(const struct device *d) {
    fake_stops++;
    if (fake_done) {
        fake_done(d, -ECANCELED, 0);
        fake_done = 0;
    }
    return 0;
}
static inline int can_start(const struct device *d) {
    (void)d;
    return 0;
}
static inline int can_set_mode(const struct device *d, int m) {
    (void)d;
    fake_mode = m;
    return 0;
}
static inline int can_calc_timing(const struct device *d, struct can_timing *t, uint32_t rate,
                                  uint16_t sp) {
    (void)d;
    if (rate != 500000 || sp != 875)
        return -EINVAL;
    *t = (struct can_timing){0, 13, 2, 10};
    return 0;
}
static inline int can_calc_timing_data(const struct device *d, struct can_timing *t, uint32_t rate,
                                       uint16_t sp) {
    (void)d;
    if (rate != 2000000 || sp != 800)
        return -EINVAL;
    *t = (struct can_timing){0, 15, 4, 2};
    return 0;
}
static inline int can_get_core_clock(const struct device *d, uint32_t *c) {
    (void)d;
    *c = 80000000;
    return 0;
}
static inline int can_set_timing(const struct device *d, struct can_timing *t) {
    (void)d;
    (void)t;
    return 0;
}
static inline int can_set_timing_data(const struct device *d, struct can_timing *t) {
    (void)d;
    (void)t;
    return 0;
}
static inline int can_send(const struct device *d, const struct can_frame *f, int timeout,
                           void (*cb)(const struct device *, int, void *), void *arg) {
    (void)d;
    (void)f;
    (void)timeout;
    (void)arg;
    fake_sends++;
    fake_done = cb;
    return 0;
}
static inline int can_add_rx_filter(const struct device *d,
                                    void (*cb)(const struct device *, struct can_frame *, void *),
                                    void *arg, struct can_filter *f) {
    (void)d;
    (void)cb;
    (void)arg;
    (void)f;
    return 0;
}
static inline int can_get_state(const struct device *d, enum can_state *s,
                                struct can_bus_err_cnt *c) {
    (void)d;
    *s = CAN_STATE_ERROR_ACTIVE;
    c->tx_err_cnt = c->rx_err_cnt = 0;
    return 0;
}

#define can_stats_get_bit_errors(d) 0U
#define can_stats_get_stuff_errors(d) 0U
#define can_stats_get_form_errors(d) 0U
#define can_stats_get_ack_errors(d) 0U
