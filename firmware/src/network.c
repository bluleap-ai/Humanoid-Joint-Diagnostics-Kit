#include "app.h"
#include "wifi_config.h"
#include <soc.h>
#include <esp_wifi.h>
#include "device_credentials.h"
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/net/net_if.h>
#include <zephyr/net/dhcpv4.h>
#include <zephyr/net/dhcpv4_server.h>
#include <zephyr/net/hostname.h>
#include <zephyr/net/net_ip.h>
#include <zephyr/net/wifi_mgmt.h>
#include <zephyr/settings/settings.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/reboot.h>

static struct wifi_saved saved;
static struct net_if *iface;
static struct net_mgmt_event_callback wifi_cb;
static atomic_t last_error, connected, ready, radio_ready;
static struct wifi_connect_req_params params;
static const struct gpio_dt_spec recovery = GPIO_DT_SPEC_GET(DT_PATH(zephyr_user), recovery_gpios);
static int load(const char *name, size_t len, settings_read_cb read, void *arg) {
    if (strcmp(name, "wifi") || (len != sizeof(saved) && len != offsetof(struct wifi_saved, band)))
        return -ENOENT;
    struct wifi_saved candidate = {0};
    int n = read(arg, &candidate, len);
    if (n != len || wifi_saved_validate(&candidate))
        return -EINVAL;
    saved = candidate;
    return 0;
}
SETTINGS_STATIC_HANDLER_DEFINE(wcan, "wcan", NULL, load, NULL, NULL);
static void wifi_event(struct net_mgmt_event_callback *cb, uint64_t event, struct net_if *i) {
    ARG_UNUSED(i);
    if (event == NET_EVENT_WIFI_CONNECT_RESULT || event == NET_EVENT_WIFI_AP_ENABLE_RESULT) {
        const struct wifi_status *status = cb->info;
        atomic_set(&last_error, status ? status->status : -EIO);
        atomic_set(&connected, status && status->status == 0);
    } else if (event == NET_EVENT_WIFI_DISCONNECT_RESULT) {
        atomic_set(&connected, 0);
        atomic_set(&last_error, -ENETDOWN);
        /* Lease task independently bounds any application transmissions. */
    }
}
const char *network_mode(void) { return saved.station ? "station" : "ap"; }
int network_error(void) { return atomic_get(&last_error); }
int network_provision(const uint8_t *p, size_t n) {
    struct wifi_saved candidate;
    int err = wifi_payload_parse(p, n, &candidate);
    if (err)
        return err;
    capture_stop();
    return settings_save_one("wcan/wifi", &candidate, sizeof(candidate));
}
static void recovery_thread(void *a, void *b, void *c) {
    ARG_UNUSED(a);
    ARG_UNUSED(b);
    ARG_UNUSED(c);
    bool released = false;
    int64_t pressed = 0, last_retry = 0;
    while (!atomic_get(&ready))
        k_sleep(K_MSEC(100));
    k_sleep(K_SECONDS(5)); /* never use a held boot strap as an application action */
    while (1) {
        int level = gpio_pin_get_dt(&recovery);
        if (level == 0) {
            released = true;
            pressed = 0;
        }
        if (level > 0 && released) {
            if (!pressed)
                pressed = k_uptime_get();
            if (k_uptime_get() - pressed >= 3000) {
                capture_stop();
                struct wifi_saved ap = {0};
                if (settings_save_one("wcan/wifi", &ap, sizeof(ap)) == 0)
                    sys_reboot(SYS_REBOOT_COLD);
            }
        }
        if (atomic_get(&radio_ready) && saved.station && !atomic_get(&connected) &&
            k_uptime_get() - last_retry > 15000) {
            capture_stop();
            int err = net_mgmt(NET_REQUEST_WIFI_CONNECT, iface, &params, sizeof(params));
            if (err)
                atomic_set(&last_error, err);
            last_retry = k_uptime_get();
        }
        k_sleep(K_MSEC(100));
    }
}
K_THREAD_DEFINE(recovery_task, 2048, recovery_thread, NULL, NULL, NULL, 7, 0, 0);
int network_init(void) {
    int err = settings_subsys_init();
    if (err)
        return err;
    err = settings_load_subtree("wcan");
    if (err)
        return err;
    if (!gpio_is_ready_dt(&recovery))
        return -ENODEV;
    err = gpio_pin_configure_dt(&recovery, GPIO_INPUT);
    if (err)
        return err;
    net_mgmt_init_event_callback(&wifi_cb, wifi_event,
                                 NET_EVENT_WIFI_CONNECT_RESULT | NET_EVENT_WIFI_DISCONNECT_RESULT |
                                     NET_EVENT_WIFI_AP_ENABLE_RESULT);
    net_mgmt_add_event_callback(&wifi_cb);
    char host[32];
    snprintf(host, sizeof(host), "can-%s", device_id);
    net_hostname_set(host, strlen(host));
    iface = net_if_get_default();
    if (!iface)
        return -ENODEV;
    params = (struct wifi_connect_req_params){
        .ssid = (const uint8_t *)(saved.station ? saved.ssid : ap_ssid),
        .psk = (const uint8_t *)(saved.station ? saved.password : ap_password),
        .security = WIFI_SECURITY_TYPE_PSK,
        .channel = saved.station ? WIFI_CHANNEL_ANY
                                 : (saved.channel ? saved.channel : (saved.band ? 36 : 6)),
        .band = saved.band ? WIFI_FREQ_BAND_5_GHZ : WIFI_FREQ_BAND_2_4_GHZ,
        .mfp = WIFI_MFP_OPTIONAL,
        .timeout = 10};
    params.ssid_length = strlen((const char *)params.ssid);
    params.psk_length = strlen((const char *)params.psk);
    /* The pinned Zephyr ESP32 driver ignores params.band. Apply the HAL band
     * explicitly before association/AP startup; its device init already started
     * Wi-Fi in NULL mode. Never silently fall back to the other band. */
    err = esp_wifi_set_country_code(saved.country[0] ? saved.country : "01", false);
    if (!err)
        err = esp_wifi_set_band_mode(saved.band ? WIFI_BAND_MODE_5G_ONLY : WIFI_BAND_MODE_2G_ONLY);
    if (err) {
        atomic_set(&last_error, -err);
        atomic_set(&ready, 1); /* physical recovery must still work */
        return 0;
    }
    atomic_set(&radio_ready, 1);
    if (saved.station) {
        net_dhcpv4_start(iface);
        err = net_mgmt(NET_REQUEST_WIFI_CONNECT, iface, &params, sizeof(params));
    } else {
        struct net_in_addr ip, mask, pool;
        net_addr_pton(NET_AF_INET, "192.168.4.1", &ip);
        net_addr_pton(NET_AF_INET, "255.255.255.0", &mask);
        net_addr_pton(NET_AF_INET, "192.168.4.10", &pool);
        if (!net_if_ipv4_addr_add(iface, &ip, NET_ADDR_MANUAL, 0))
            return -EIO;
        net_if_ipv4_set_netmask_by_addr(iface, &ip, &mask);
        err = net_mgmt(NET_REQUEST_WIFI_AP_ENABLE, iface, &params, sizeof(params));
        if (!err)
            err = net_dhcpv4_server_start(iface, &pool);
    }
    atomic_set(&last_error, err);
    atomic_set(&ready, 1);
    return 0; /* failure remains observable; physical recovery remains available
               */
}

size_t network_status(char *out, size_t size) {
    char address[NET_IPV4_ADDR_LEN] = "unassigned";
    struct net_in_addr *ip = iface ? net_if_ipv4_get_global_addr(iface, NET_ADDR_PREFERRED) : NULL;
    if (ip)
        net_addr_ntop(NET_AF_INET, ip, address, sizeof(address));
    struct wifi_iface_status status = {0};
    bool up = atomic_get(&connected);
    bool known = up && !net_mgmt(NET_REQUEST_WIFI_IFACE_STATUS, iface, &status, sizeof(status));
    const char *band = known && status.band == WIFI_FREQ_BAND_5_GHZ     ? "\"5GHz\""
                       : known && status.band == WIFI_FREQ_BAND_2_4_GHZ ? "\"2.4GHz\""
                                                                        : "null";
    const char *phy = known && saved.station && status.link_mode == WIFI_6   ? "\"802.11ax\""
                      : known && saved.station && status.link_mode == WIFI_4 ? "\"802.11n\""
                                                                             : "null";
    int n = snprintf(out, size,
                     "\"wifi_connected\":%s,\"ip\":\"%s\",\"wifi_band_requested\":\"%s\","
                     "\"wifi_band\":%s,\"wifi_channel\":%u,\"wifi_phy\":%s,\"wifi_country\":\"%s\"",
                     up ? "true" : "false", address, saved.band ? "5GHz" : "2.4GHz", band,
                     known ? status.channel : 0, phy, saved.country[0] ? saved.country : "01");
    return n < 0 ? 0 : MIN((size_t)n, size - 1);
}
