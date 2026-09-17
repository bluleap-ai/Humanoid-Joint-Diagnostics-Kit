#pragma once
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#define CONFIG_WCAN_RX_DEPTH 2
#define CONFIG_SYS_CLOCK_TICKS_PER_SEC 1000
#define CONFIG_WCAN_TX_EVENT_DEPTH 8
#define CONFIG_WCAN_SLNT 1
#define ARG_UNUSED(x) (void)(x)
#define IS_ENABLED(x) (x)
#define MAX(a, b) ((a) > (b) ? (a) : (b))
#define MIN(a, b) ((a) < (b) ? (a) : (b))
#define K_NO_WAIT 0
#define K_FOREVER -1
#define K_MSEC(x) (x)
#define K_THREAD_DEFINE(...)
#define K_MUTEX_DEFINE(n) int n
struct k_spinlock {
    int unused;
};
typedef int k_spinlock_key_t;
static inline int k_spin_lock(struct k_spinlock *l) {
    (void)l;
    return 0;
}
static inline void k_spin_unlock(struct k_spinlock *l, int k) {
    (void)l;
    (void)k;
}
static inline void k_mutex_lock(int *l, int t) {
    (void)l;
    (void)t;
}
static inline void k_mutex_unlock(int *l) { (void)l; }
static int64_t fake_now;
static inline int64_t k_uptime_get(void) { return fake_now; }
static inline uint64_t k_uptime_ticks(void) { return fake_now; }
static inline uint64_t k_ticks_to_us_floor64(uint64_t t) { return t * 1000; }
static inline void k_sleep(int ms) { fake_now += ms; }
struct k_msgq {
    unsigned size, capacity, count, head;
    unsigned char *data;
};
#define K_MSGQ_DEFINE(n, s, c, a)                                                                  \
    static unsigned char n##_buf[(s) * (c)];                                                       \
    struct k_msgq n = {s, c, 0, 0, n##_buf}
static inline int k_msgq_put(struct k_msgq *q, const void *p, int t) {
    (void)t;
    if (q->count == q->capacity)
        return -ENOSPC;
    memcpy(q->data + ((q->head + q->count) % q->capacity) * q->size, p, q->size);
    q->count++;
    return 0;
}
static inline int k_msgq_get(struct k_msgq *q, void *p, int t) {
    (void)t;
    if (!q->count)
        return -EAGAIN;
    memcpy(p, q->data + q->head * q->size, q->size);
    q->head = (q->head + 1) % q->capacity;
    q->count--;
    return 0;
}
static inline unsigned k_msgq_num_used_get(struct k_msgq *q) { return q->count; }
static inline void k_msgq_purge(struct k_msgq *q) { q->head = q->count = 0; }
