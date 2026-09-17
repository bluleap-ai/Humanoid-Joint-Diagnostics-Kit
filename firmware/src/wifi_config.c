#include "wifi_config.h"
#include <errno.h>
#include <stdbool.h>
#include <string.h>
int wifi_saved_validate(const struct wifi_saved *c) {
    if (c->station > 1 || c->band > 1 || c->ssid[32] || c->password[63] || c->country[2])
        return -EINVAL;
    if (c->country[0]) {
        static const char countries[] =
            "AT AU BE BG BR CA CH CN CY CZ DE DK EE ES FI FR GB GR HK HR HU IE IN IS IT JP KR LI "
            "LT LU LV MT MX NL NO NZ PL PT RO SE SI SK TW US";
        bool found = false;
        for (size_t i = 0; i + 1 < sizeof(countries); i += 3)
            if (!memcmp(countries + i, c->country, 2))
                found = true;
        if (!found)
            return -ENOTSUP;
        if (c->country[0] < 'A' || c->country[0] > 'Z' || c->country[1] < 'A' ||
            c->country[1] > 'Z')
            return -EINVAL;
    } else if (c->country[1] || c->band) {
        return -EINVAL;
    }
    if (c->station && (!c->ssid[0] || strlen(c->password) < 8))
        return -EINVAL;
    if (!c->station && (c->ssid[0] || c->password[0]))
        return -EINVAL;
    if (c->station && c->channel)
        return -EINVAL; /* station scans selected band */
    if (c->channel &&
        (c->band ? !(c->channel == 36 || c->channel == 40 || c->channel == 44 || c->channel == 48)
                 : c->channel > 11))
        return -EINVAL; /* limited non-DFS AP channel set, still checked by HAL */
    return 0;
}
int wifi_payload_parse(const uint8_t *p, size_t n, struct wifi_saved *c) {
    if (n < 3)
        return -EINVAL;
    memset(c, 0, sizeof(*c));
    size_t offset = 3;
    c->station = p[0];
    if (p[0] & 0x80) {
        if (n < 7)
            return -EINVAL;
        c->station &= 0x7f;
        c->band = p[3];
        c->channel = p[4];
        memcpy(c->country, p + 5, 2);
        offset = 7;
    }
    if (p[1] > 32 || p[2] > 63 || n != offset + p[1] + p[2] || memchr(p + offset, 0, n - offset))
        return -EINVAL;
    memcpy(c->ssid, p + offset, p[1]);
    memcpy(c->password, p + offset + p[1], p[2]);
    return wifi_saved_validate(c);
}
