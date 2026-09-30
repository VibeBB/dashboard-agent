#include "dash_codec.h"

uint16_t dash_crc16(const uint8_t *data, size_t length) {
    uint16_t crc = 0xffffu;
    size_t i;
    for (i = 0; i < length; ++i) {
        unsigned bit;
        crc ^= (uint16_t)data[i] << 8;
        for (bit = 0; bit < 8u; ++bit) {
            crc = (crc & 0x8000u) != 0u
                ? (uint16_t)((crc << 1) ^ 0x1021u)
                : (uint16_t)(crc << 1);
        }
    }
    return crc;
}

size_t dash_cobs_encode(const uint8_t *input, size_t length, uint8_t *output, size_t capacity) {
    size_t read = 0u;
    size_t write = 1u;
    size_t code_index = 0u;
    uint8_t code = 1u;
    if (capacity == 0u) return 0u;
    while (read < length) {
        if (input[read] == 0u) {
            output[code_index] = code;
            code_index = write++;
            code = 1u;
        } else {
            if (write >= capacity) return 0u;
            output[write++] = input[read];
            ++code;
            if (code == 0xffu) {
                if (write >= capacity) return 0u;
                output[code_index] = code;
                code_index = write++;
                code = 1u;
            }
        }
        ++read;
    }
    if (code_index >= capacity) return 0u;
    output[code_index] = code;
    return write;
}

size_t dash_cobs_decode(const uint8_t *input, size_t length, uint8_t *output, size_t capacity) {
    size_t read = 0u;
    size_t write = 0u;
    while (read < length) {
        uint8_t code = input[read++];
        size_t count;
        if (code == 0u) return 0u;
        count = (size_t)code - 1u;
        if (read + count > length || write + count > capacity) return 0u;
        while (count-- > 0u) output[write++] = input[read++];
        if (code != 0xffu && read < length) {
            if (write >= capacity) return 0u;
            output[write++] = 0u;
        }
    }
    return write;
}
