#pragma once
#include <stddef.h>
#include <stdint.h>
struct wifi_saved {
    uint8_t station;
    char ssid[33];
    char password[64];
    uint8_t band;    /* 0: 2.4 GHz, 1: 5 GHz */
    uint8_t channel; /* zero: station scan or AP default */
    char country[3]; /* empty: factory world domain */
};
int wifi_saved_validate(const struct wifi_saved *cfg);
int wifi_payload_parse(const uint8_t *p, size_t n, struct wifi_saved *cfg);
