#pragma once
typedef int atomic_t;
static inline int atomic_get(atomic_t *v) { return *v; }
static inline void atomic_set(atomic_t *v, int n) { *v = n; }
static inline void atomic_clear(atomic_t *v) { *v = 0; }
static inline void atomic_inc(atomic_t *v) { ++*v; }
static inline int atomic_cas(atomic_t *v, int old, int n) {
    if (*v != old)
        return 0;
    *v = n;
    return 1;
}
