#include "app.h"
#include <stdio.h>
#include <string.h>
#include <zephyr/drivers/can.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/sys/atomic.h>

static const struct device *can = DEVICE_DT_GET(DT_ALIAS(canbus));
static const struct gpio_dt_spec slnt = GPIO_DT_SPEC_GET(DT_PATH(zephyr_user), slnt_gpios);
K_MSGQ_DEFINE(rx_queue, sizeof(struct w_frame), CONFIG_WCAN_RX_DEPTH, 4);
K_MSGQ_DEFINE(tx_events, sizeof(struct tx_event), CONFIG_WCAN_TX_EVENT_DEPTH, 4);
K_MUTEX_DEFINE(control);
static struct k_spinlock stats_lock;
static uint64_t received, enqueued, drops, discards, sequence;
static uint32_t highwater;
static atomic_t tx_event_drops;
static bool running, scheduled, inflight, configured;
static uint32_t tx_request, remaining, completed, interval_ms;
static int64_t next_send, lease_deadline, tx_deadline;
static struct can_frame outgoing;
static atomic_t completion_ready, completion_error;
struct capture_config applied = {
    .bitrate = 500000, .sp = 875, .data_bitrate = 2000000, .data_sp = 800};

static void silent(bool yes) {
    if (IS_ENABLED(CONFIG_WCAN_SLNT))
        gpio_pin_set_dt(&slnt, yes);
}
static void event(int error, bool terminal) {
    struct tx_event e = {tx_request, completed, error, terminal};
    if (k_msgq_put(&tx_events, &e, K_NO_WAIT))
        atomic_inc(&tx_event_drops);
}
static void rx(const struct device *dev, struct can_frame *f, void *arg) {
    ARG_UNUSED(dev);
    ARG_UNUSED(arg);
    struct w_frame rec = {
        .us = k_ticks_to_us_floor64(k_uptime_ticks()), .id = f->id, .dlc = f->dlc};
    rec.flags = ((f->flags & CAN_FRAME_IDE) ? W_EXT : 0) | ((f->flags & CAN_FRAME_FDF) ? W_FD : 0) |
                ((f->flags & CAN_FRAME_BRS) ? W_BRS : 0) |
                ((f->flags & CAN_FRAME_ESI) ? W_ESI : 0) | ((f->flags & CAN_FRAME_RTR) ? W_RTR : 0);
    rec.len = (rec.flags & W_RTR) ? 0 : ((rec.flags & W_FD) ? w_length(rec.dlc) : MIN(rec.dlc, 8));
    if (rec.len > 64)
        return;
    memcpy(rec.data, f->data, rec.len);
    k_spinlock_key_t key = k_spin_lock(&stats_lock);
    rec.seq = ++sequence;
    received++;
    if (k_msgq_put(&rx_queue, &rec, K_NO_WAIT))
        drops++;
    else {
        enqueued++;
        highwater = MAX(highwater, k_msgq_num_used_get(&rx_queue));
    }
    k_spin_unlock(&stats_lock, key);
}
static void tx_done(const struct device *dev, int error, void *arg) {
    ARG_UNUSED(dev);
    ARG_UNUSED(arg);
    atomic_set(&completion_error, error);
    atomic_set(&completion_ready, 1);
}
static void stop_locked(void) {
    silent(true);
    bool uncertain = inflight;
    if (running)
        can_stop(can); /* pinned driver aborts hardware TX buffers */
    running = false;
    if (scheduled || inflight)
        event(uncertain ? -EINPROGRESS : -ECANCELED, true);
    scheduled = false;
    inflight = false;
    remaining = 0;
    atomic_clear(&completion_ready);
    applied.active = false;
}
void capture_stop(void) {
    k_mutex_lock(&control, K_FOREVER);
    stop_locked();
    k_mutex_unlock(&control);
}
void capture_cancel(void) { capture_stop(); }
void capture_lease(void) {
    k_mutex_lock(&control, K_FOREVER);
    lease_deadline = k_uptime_get() + 3000;
    k_mutex_unlock(&control);
}
void capture_discard_tx(unsigned n) {
    while (n--)
        atomic_inc(&tx_event_drops);
}
void capture_discard(unsigned n) {
    k_spinlock_key_t key = k_spin_lock(&stats_lock);
    discards += n;
    k_spin_unlock(&stats_lock, key);
}
static int timing(uint32_t rate, uint16_t sp, bool data, struct can_timing *t) {
    uint32_t clock;
    if (sp < 500 || sp > 950 || rate < 10000 || rate > (data ? 5000000 : 1000000))
        return -EINVAL;
    int err = data ? can_calc_timing_data(can, t, rate, sp) : can_calc_timing(can, t, rate, sp);
    if (err != 0)
        return -ERANGE; /* reject sample point approximation */
    err = can_get_core_clock(can, &clock);
    uint32_t quanta = 1 + t->prop_seg + t->phase_seg1 + t->phase_seg2;
    if (err || clock != (uint64_t)rate * t->prescaler * quanta ||
        (1 + t->prop_seg + t->phase_seg1) * 1000U != sp * quanta)
        return -ERANGE;
    return 0;
}
int capture_configure(const struct capture_config *cfg) {
    k_mutex_lock(&control, K_FOREVER);
    stop_locked();
    configured = false;
    struct can_timing nominal = {0}, data = {0};
    int err = timing(cfg->bitrate, cfg->sp, false, &nominal);
    if (!err && cfg->fd)
        err = timing(cfg->data_bitrate, cfg->data_sp, true, &data);
    if (!err)
        err = can_set_mode(can, (cfg->active ? 0 : CAN_MODE_LISTENONLY) |
                                    (cfg->fd ? CAN_MODE_FD : 0) | CAN_MODE_MANUAL_RECOVERY |
                                    CAN_MODE_ONE_SHOT);
    if (!err)
        err = can_set_timing(can, &nominal);
    if (!err && cfg->fd)
        err = can_set_timing_data(can, &data);
    if (!err) {
        applied = *cfg;
        configured = true;
    }
    k_mutex_unlock(&control);
    return err;
}
int capture_start(void) {
    k_mutex_lock(&control, K_FOREVER);
    int err = running ? -EALREADY
                      : (!configured
                             ? -EINVAL
                             : can_set_mode(can, (applied.active ? 0 : CAN_MODE_LISTENONLY) |
                                                     (applied.fd ? CAN_MODE_FD : 0) |
                                                     CAN_MODE_MANUAL_RECOVERY | CAN_MODE_ONE_SHOT));
    if (!err)
        err = can_start(can);
    if (!err) {
        running = true;
        silent(!applied.active);
        lease_deadline = k_uptime_get() + 3000;
    }
    k_mutex_unlock(&control);
    return err;
}
int capture_tx(const struct w_frame *f, uint32_t interval, uint32_t count, uint32_t request) {
    if (w_validate(f, true) || !count || count > 10000 || interval > 60000 ||
        (count > 1 && interval < 10))
        return -EINVAL;
    k_mutex_lock(&control, K_FOREVER);
    int err = 0;
    if (!running || !applied.active)
        err = -EPERM;
    else if (scheduled || inflight)
        err = -EBUSY;
    else if ((f->flags & W_FD) && !applied.fd)
        err = -EINVAL;
    else {
        outgoing = (struct can_frame){.id = f->id,
                                      .dlc = f->dlc,
                                      .flags = ((f->flags & W_EXT) ? CAN_FRAME_IDE : 0) |
                                               ((f->flags & W_FD) ? CAN_FRAME_FDF : 0) |
                                               ((f->flags & W_BRS) ? CAN_FRAME_BRS : 0) |
                                               ((f->flags & W_RTR) ? CAN_FRAME_RTR : 0)};
        memcpy(outgoing.data, f->data, f->len);
        tx_request = request;
        remaining = count;
        completed = 0;
        interval_ms = interval;
        next_send = k_uptime_get();
        scheduled = true;
    }
    k_mutex_unlock(&control);
    return err;
}
static void scheduler_tick(void) {
    k_mutex_lock(&control, K_FOREVER);
    int64_t now = k_uptime_get();
    if (running && now > lease_deadline)
        stop_locked();
    if (inflight && atomic_cas(&completion_ready, 1, 0)) {
        int err = atomic_get(&completion_error);
        inflight = false;
        if (!err)
            completed++;
        event(err, err || !remaining);
        if (err || !remaining)
            scheduled = false;
    }
    if (inflight && now > tx_deadline)
        stop_locked();
    if (scheduled && !inflight && now >= next_send) {
        remaining--;
        inflight = true;
        tx_deadline = now + 1000;
        int err = can_send(can, &outgoing, K_NO_WAIT, tx_done, NULL);
        if (err) {
            inflight = false;
            scheduled = false;
            event(err, true);
        }
        next_send = now + interval_ms; /* no catch-up burst */
    }
    k_mutex_unlock(&control);
}
static void scheduler(void *a, void *b, void *c) {
    ARG_UNUSED(a);
    ARG_UNUSED(b);
    ARG_UNUSED(c);
    while (1) {
        scheduler_tick();
        k_sleep(K_MSEC(2));
    }
}
K_THREAD_DEFINE(tx_scheduler, 2048, scheduler, NULL, NULL, NULL, 5, 0, 0);
int capture_init(void) {
    if (!device_is_ready(can))
        return -ENODEV;
    if (IS_ENABLED(CONFIG_WCAN_SLNT)) {
        if (!gpio_is_ready_dt(&slnt))
            return -ENODEV;
        int err = gpio_pin_configure_dt(&slnt, GPIO_OUTPUT_ACTIVE);
        if (err)
            return err;
    }
    struct can_filter standard = {.id = 0, .mask = 0},
                      extended = {.id = 0, .mask = 0, .flags = CAN_FILTER_IDE};
    int s = can_add_rx_filter(can, rx, NULL, &standard),
        e = can_add_rx_filter(can, rx, NULL, &extended);
    if (s < 0 || e < 0)
        return -ENOSPC;
    struct capture_config defaults = applied;
    return capture_configure(&defaults);
}
size_t capture_status(char *out, size_t size) {
    enum can_state state;
    struct can_bus_err_cnt counts = {0};
    k_mutex_lock(&control, K_FOREVER);
    int err = can_get_state(can, &state, &counts);
    k_spinlock_key_t key = k_spin_lock(&stats_lock);
    uint64_t r = received, e = enqueued, d = drops, t = discards, s = sequence;
    uint32_t high = highwater;
    k_spin_unlock(&stats_lock, key);
    int n = snprintf(out, size,
                     "\"capture\":%s,\"active\":%s,\"hardware_silent\":%s,\"fd\":%s,"
                     "\"bitrate\":%u,\"sample_point\":%u,\"data_bitrate\":%u,\"data_sample_"
                     "point\":%u,\"received\":%llu,\"enqueued\":%llu,\"queue_drops\":%llu,"
                     "\"transport_discards\":%llu,\"queue_used\":%u,\"queue_highwater\":%u,"
                     "\"last_sequence\":%llu,\"controller_state\":%d,\"rx_errors\":%u,\"tx_"
                     "errors\":%u,\"state_read_error\":%d,\"hardware_rx_losses\":null,\"bus_"
                     "error_events\":null,\"tx_event_discards\":%ld,\"hardware_filters\":null,"
                     "\"capture_filter\":\"all_standard_and_extended\",\"timestamp_method\":"
                     "\"callback_kernel_ticks_us\"",
                     running ? "true" : "false", applied.active ? "true" : "false",
                     IS_ENABLED(CONFIG_WCAN_SLNT) ? "true" : "false", applied.fd ? "true" : "false",
                     applied.bitrate, applied.sp, applied.data_bitrate, applied.data_sp,
                     (unsigned long long)r, (unsigned long long)e, (unsigned long long)d,
                     (unsigned long long)t, k_msgq_num_used_get(&rx_queue), high,
                     (unsigned long long)s, err ? -1 : state, counts.rx_err_cnt, counts.tx_err_cnt,
                     err, (long)atomic_get(&tx_event_drops));
    if (n > 0 && (size_t)n < size)
        n += snprintf(out + n, size - n,
                      ",\"configured\":%s,\"timestamp_resolution_us\":%u,\"bus_bit_errors\":%"
                      "u,\"bus_stuff_errors\":%u,\"bus_form_errors\":%u,\"bus_ack_errors\":%"
                      "u,\"bus_crc_errors\":null",
                      configured ? "true" : "false", 1000000 / CONFIG_SYS_CLOCK_TICKS_PER_SEC,
                      can_stats_get_bit_errors(can), can_stats_get_stuff_errors(can),
                      can_stats_get_form_errors(can), can_stats_get_ack_errors(can));
    k_mutex_unlock(&control);
    return n < 0 ? 0 : MIN((size_t)n, size - 1);
}
