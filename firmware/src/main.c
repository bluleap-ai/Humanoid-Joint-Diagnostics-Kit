#include "app.h"
#include "device_credentials.h"
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <zephyr/net/dns_sd.h>
#include <zephyr/net/socket.h>
#include <zephyr/net/tls_credentials.h>
#include <zephyr/random/random.h>
#include <zephyr/sys/reboot.h>

uint64_t boot_session;
DNS_SD_REGISTER_TCP_SERVICE(wcan, ap_ssid, "_wcan", "local", DNS_SD_EMPTY_TXT, 7443);
static uint8_t input[W_HEADER + W_MAX], output[W_HEADER + W_MAX];
static char response[2048];
static int send_packet(int fd, uint8_t kind, uint32_t request, const void *data, size_t len) {
    if (len > W_MAX)
        return -EMSGSIZE;
    struct w_header h = {kind, len, request, boot_session};
    w_header_encode(output, &h);
    memcpy(output + W_HEADER, data, len);
    size_t sent = 0;
    int64_t deadline = k_uptime_get() + 750;
    while (sent < len + W_HEADER && k_uptime_get() < deadline) {
        int n = zsock_send(fd, output + sent, len + W_HEADER - sent, 0);
        if (n <= 0)
            return -EIO;
        sent += n;
    }
    return sent == len + W_HEADER ? 0 : -ETIMEDOUT;
}
static void info_json(char *buf, size_t size) {
    int n =
        snprintf(buf, size,
                 "{\"ok\":true,\"firmware\":\"0.1.0-zephyr\",\"protocol\":1,"
                 "\"device\":\"%s\",\"session\":%llu,\"wifi_mode\":\"%s\","
                 "\"wifi_provision_version\":2,\"wifi_error\":%d,\"lease_ms\":3000,\"channels\":1,",
                 device_id, (unsigned long long)boot_session, network_mode(), network_error());
    n += capture_status(buf + n, size - n);
    if ((size_t)n + 2 < size) {
        buf[n++] = ',';
        n += network_status(buf + n, size - n);
    }
    if ((size_t)n + 2 < size) {
        buf[n++] = '}';
        buf[n] = 0;
    }
}
static void discard_queue(void) {
    struct w_frame f;
    unsigned n = 0;
    while (!k_msgq_get(&rx_queue, &f, K_NO_WAIT))
        n++;
    capture_discard(n);
    capture_discard_tx(k_msgq_num_used_get(&tx_events));
    k_msgq_purge(&tx_events);
}
static int command(const struct w_header *h, const uint8_t *p, bool *reboot) {
    int err = 0;
    switch (h->kind) {
    case 1:
    case 2:
    case 9:
        if (h->length)
            err = -EINVAL;
        break;
    case 3: {
        if (h->length != 14 || p[0] > 1 || p[1] > 1) {
            err = -EINVAL;
            break;
        }
        struct capture_config c = {.fd = p[0],
                                   .active = p[1],
                                   .bitrate = r32(p + 2),
                                   .sp = r16(p + 6),
                                   .data_bitrate = r32(p + 8),
                                   .data_sp = r16(p + 12)};
        err = capture_configure(&c);
        discard_queue();
        break;
    }
    case 4:
        if (h->length)
            err = -EINVAL;
        else
            err = capture_start();
        break;
    case 5:
    case 7:
        if (h->length)
            err = -EINVAL;
        else
            capture_stop();
        break;
    case 6: {
        if (h->length < 16 || h->length > 80 || p[15] || p[14] > 64 || h->length != 16U + p[14]) {
            err = -EINVAL;
            break;
        }
        struct w_frame f = {.id = r32(p + 8), .flags = p[12], .dlc = p[13], .len = p[14]};
        memcpy(f.data, p + 16, f.len);
        err = capture_tx(&f, r32(p), r32(p + 4), h->request);
        break;
    }
    case 8:
        err = network_provision(p, h->length);
        *reboot = !err;
        break;
    default:
        err = -ENOTSUP;
    }
    if (err)
        snprintf(response, sizeof(response),
                 "{\"ok\":false,\"error\":\"command rejected\",\"code\":%d}", err);
    else if (h->kind == 1 || h->kind == 2 || h->kind == 3)
        info_json(response, sizeof(response));
    else
        snprintf(response, sizeof(response), "{\"ok\":true,\"request\":%u,\"state\":\"%s\"}",
                 h->request, h->kind == 6 ? "accepted" : "applied");
    return err;
}
static void serve(int fd) {
    bool hello = false, reboot = false;
    size_t used = 0;
    uint32_t high_request = 0;
    int64_t partial_since = 0, last_status = 0, last_command = k_uptime_get();
    struct {
        uint32_t id;
        uint8_t kind;
        uint32_t len;
        uint8_t payload[96];
        char reply[2048];
    } cache = {0};
    capture_stop();
    discard_queue();
    while (1) {
        if (k_uptime_get() - last_command > 3000)
            break;
        struct zsock_pollfd poll = {.fd = fd, .events = ZSOCK_POLLIN};
        /* Avoid a fixed 10 ms batching ceiling when records are already waiting.
         * Still block briefly so lower-priority lease/TX work can run. */
        int timeout_ms =
            (k_msgq_num_used_get(&rx_queue) || k_msgq_num_used_get(&tx_events)) ? 1 : 10;
        int ready = zsock_poll(&poll, 1, timeout_ms);
        if (ready < 0 || (poll.revents & (ZSOCK_POLLERR | ZSOCK_POLLHUP | ZSOCK_POLLNVAL)))
            break;
        if (ready > 0 && (poll.revents & ZSOCK_POLLIN)) {
            int n = zsock_recv(fd, input + used, sizeof(input) - used, 0);
            if (n <= 0)
                break;
            if (!used)
                partial_since = k_uptime_get();
            used += n;
        }
        while (used >= W_HEADER) {
            struct w_header h;
            if (w_parse(input, &h) || !h.request)
                goto done;
            if (used < W_HEADER + h.length)
                break;
            const uint8_t *payload = input + W_HEADER;
            if ((!hello && (h.kind != 1 || h.session)) || (hello && h.session != boot_session))
                goto done;
            if (h.request <= high_request) {
                if (h.request == cache.id && h.kind == cache.kind && h.length == cache.len &&
                    h.length <= sizeof(cache.payload) && !memcmp(cache.payload, payload, h.length))
                    strcpy(response, cache.reply);
                else
                    snprintf(response, sizeof(response),
                             "{\"ok\":false,\"error\":\"duplicate or stale request; not "
                             "executed\"}");
            } else {
                high_request = h.request;
                if (h.kind == 1 && hello)
                    goto done;
                command(&h, payload, &reboot);
                if (h.kind == 1)
                    hello = true;
                cache.id = h.request;
                cache.kind = h.kind;
                cache.len = h.length;
                if (h.length <= sizeof(cache.payload))
                    memcpy(cache.payload, payload, h.length);
                strcpy(cache.reply, response);
            }
            last_command = k_uptime_get();
            capture_lease();
            if (send_packet(fd, 128, h.request, response, strlen(response)))
                goto done;
            size_t consumed = W_HEADER + h.length;
            used -= consumed;
            memmove(input, input + consumed, used);
            partial_since = k_uptime_get();
            if (reboot) {
                capture_stop();
                k_sleep(K_MSEC(100));
                sys_reboot(SYS_REBOOT_COLD);
            }
        }
        if (used && k_uptime_get() - partial_since > 2000)
            break;
        if (!hello)
            continue;
        uint8_t batch[16 * 88];
        size_t len = 0;
        unsigned frames = 0;
        struct w_frame f;
        while (frames < 16 && !k_msgq_get(&rx_queue, &f, K_NO_WAIT)) {
            len += w_encode(batch + len, &f);
            frames++;
        }
        if (frames && send_packet(fd, 130, 0, batch, len)) {
            capture_discard(frames);
            break;
        }
        struct tx_event event;
        while (!k_msgq_get(&tx_events, &event, K_NO_WAIT)) {
            snprintf(response, sizeof(response),
                     "{\"request\":%u,\"completed\":%u,\"state\":\"%s\",\"error\":%d,"
                     "\"terminal\":%s}",
                     event.request, event.completed,
                     event.error == -EINPROGRESS ? "indeterminate"
                     : event.error == -ECANCELED ? "cancelled"
                     : event.error               ? "failed"
                                                 : "completed",
                     event.error, event.terminal ? "true" : "false");
            if (send_packet(fd, 131, event.request, response, strlen(response))) {
                capture_discard_tx(1);
                goto done;
            }
        }
        if (k_uptime_get() - last_status >= 1000) {
            info_json(response, sizeof(response));
            if (send_packet(fd, 129, 0, response, strlen(response)))
                break;
            last_status = k_uptime_get();
        }
    }
done:
    capture_stop();
    discard_queue();
    memset(input, 0, sizeof(input));
    memset(&cache, 0, sizeof(cache));
}
void server_run(void) {
    sec_tag_t tag = 1;
    int verify = TLS_PEER_VERIFY_REQUIRED;
    if (tls_credential_add(tag, TLS_CREDENTIAL_CA_CERTIFICATE, ca_pem, sizeof(ca_pem)) ||
        tls_credential_add(tag, TLS_CREDENTIAL_PUBLIC_CERTIFICATE, server_pem,
                           sizeof(server_pem)) ||
        tls_credential_add(tag, TLS_CREDENTIAL_PRIVATE_KEY, server_key_pem, sizeof(server_key_pem)))
        return;
    int fd = zsock_socket(AF_INET, SOCK_STREAM, IPPROTO_TLS_1_2);
    if (fd < 0)
        return;
    if (zsock_setsockopt(fd, SOL_TLS, TLS_SEC_TAG_LIST, &tag, sizeof(tag)) ||
        zsock_setsockopt(fd, SOL_TLS, TLS_PEER_VERIFY, &verify, sizeof(verify))) {
        zsock_close(fd);
        return;
    }
    struct timeval timeout = {.tv_sec = 1};
    zsock_setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
    zsock_setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout));
    struct sockaddr_in address = {
        .sin_family = AF_INET, .sin_port = htons(7443), .sin_addr.s_addr = htonl(INADDR_ANY)};
    if (zsock_bind(fd, (struct sockaddr *)&address, sizeof(address)) || zsock_listen(fd, 1)) {
        zsock_close(fd);
        return;
    }
    while (1) {
        int client = zsock_accept(fd, NULL, NULL);
        if (client < 0) {
            k_sleep(K_MSEC(100));
            continue;
        }
        zsock_setsockopt(client, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
        zsock_setsockopt(client, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout));
        serve(client);
        zsock_close(client);
    }
}
int main(void) {
    if (sys_csrand_get(&boot_session, sizeof(boot_session)))
        return -EIO;
    if (!boot_session)
        boot_session = 1;
    int err = capture_init();
    if (err) {
        printk("CAN initialization failed: %d\n", err);
        return err;
    }
    err = network_init();
    if (err) {
        printk("Wi-Fi initialization failed: %d\n", err);
        return err;
    }
    printk("Wireless CAN %s: TLS TCP 7443; AP address 192.168.4.1; capture "
           "stopped\n",
           device_id);
    server_run();
    capture_stop();
    printk("TLS server failed; transmission disabled\n");
    return -EIO;
}
