#ifndef DASH_CODEC_H
#define DASH_CODEC_H

#include <stddef.h>
#include <stdint.h>

uint16_t dash_crc16(const uint8_t *data, size_t length);
size_t dash_cobs_encode(const uint8_t *input, size_t length, uint8_t *output, size_t capacity);
size_t dash_cobs_decode(const uint8_t *input, size_t length, uint8_t *output, size_t capacity);

#endif
