#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#define W_HEADER 24
#define W_MAX 4096
#define W_EXT 1
#define W_FD 2
#define W_BRS 4
#define W_ESI 8
#define W_RTR 16
struct w_header {
    uint8_t kind;
    uint32_t length, request;
    uint64_t session;
};
struct w_frame {
    uint64_t seq, us;
    uint32_t id;
    uint8_t channel, flags, dlc, len, data[64];
};
uint16_t r16(const uint8_t *p);
uint32_t r32(const uint8_t *p);
uint64_t r64(const uint8_t *p);
void w16(uint8_t *p, uint16_t v);
void w32(uint8_t *p, uint32_t v);
void w64(uint8_t *p, uint64_t v);
int w_parse(const uint8_t *p, struct w_header *h);
void w_header_encode(uint8_t *p, const struct w_header *h);
int w_validate(const struct w_frame *f, bool tx);
size_t w_encode(uint8_t *p, const struct w_frame *f);
uint8_t w_length(uint8_t dlc);
