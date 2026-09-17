#pragma once
struct gpio_dt_spec {
    int unused;
};
#define DT_PATH(x) 0
#define GPIO_DT_SPEC_GET(n, p) {0}
#define GPIO_OUTPUT_ACTIVE 1
static int fake_silent;
static inline bool gpio_is_ready_dt(const struct gpio_dt_spec *p) {
    (void)p;
    return true;
}
static inline int gpio_pin_configure_dt(const struct gpio_dt_spec *p, int f) {
    (void)p;
    fake_silent = f;
    return 0;
}
static inline int gpio_pin_set_dt(const struct gpio_dt_spec *p, int f) {
    (void)p;
    fake_silent = f;
    return 0;
}
