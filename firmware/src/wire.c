#include "wire.h"
#include <string.h>
uint16_t r16(const uint8_t *p) { return ((uint16_t)p[0] << 8) | p[1]; }
uint32_t r32(const uint8_t *p) { return ((uint32_t)r16(p) << 16) | r16(p + 2); }
uint64_t r64(const uint8_t *p) { return ((uint64_t)r32(p) << 32) | r32(p + 4); }
void w16(uint8_t *p, uint16_t v) {
    p[0] = v >> 8;
    p[1] = v;
}
void w32(uint8_t *p, uint32_t v) {
    w16(p, v >> 16);
    w16(p + 2, v);
}
void w64(uint8_t *p, uint64_t v) {
    w32(p, v >> 32);
    w32(p + 4, v);
}
uint8_t w_length(uint8_t d) {
    static const uint8_t l[] = {0, 1, 2, 3, 4, 5, 6, 7, 8, 12, 16, 20, 24, 32, 48, 64};
    return d < 16 ? l[d] : 255;
}
int w_parse(const uint8_t *p, struct w_header *h) {
    if (memcmp(p, "WCAN", 4) || p[4] != 1 || r16(p + 6) || r32(p + 8) > W_MAX || p[5] < 1 ||
        p[5] > 9)
        return -1;
    h->kind = p[5];
    h->length = r32(p + 8);
    h->request = r32(p + 12);
    h->session = r64(p + 16);
    return 0;
}
void w_header_encode(uint8_t *p, const struct w_header *h) {
    memcpy(p, "WCAN", 4);
    p[4] = 1;
    p[5] = h->kind;
    w16(p + 6, 0);
    w32(p + 8, h->length);
    w32(p + 12, h->request);
    w64(p + 16, h->session);
}
int w_validate(const struct w_frame *f, bool tx) {
    if (f->channel || f->flags & ~31 || f->dlc > 15 ||
        f->id > ((f->flags & W_EXT) ? 0x1fffffff : 0x7ff))
        return -1;
    if ((f->flags & W_FD) && (f->flags & W_RTR))
        return -1;
    if (!(f->flags & W_FD) && (f->flags & (W_BRS | W_ESI)))
        return -1;
    if (tx && ((f->flags & W_ESI) || (!(f->flags & W_FD) && f->dlc > 8)))
        return -1;
    uint8_t n =
        (f->flags & W_RTR) ? 0 : ((f->flags & W_FD) ? w_length(f->dlc) : (f->dlc < 8 ? f->dlc : 8));
    return n == f->len ? 0 : -1;
}
size_t w_encode(uint8_t *p, const struct w_frame *f) {
    w64(p, f->seq);
    w64(p + 8, f->us);
    w32(p + 16, f->id);
    p[20] = f->channel;
    p[21] = f->flags;
    p[22] = f->dlc;
    p[23] = f->len;
    memcpy(p + 24, f->data, f->len);
    return 24 + f->len;
}
