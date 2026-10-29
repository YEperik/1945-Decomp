#include "tim_image.h"

#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

static uint32_t g_random = UINT32_C(0x1945a17e);

static uint32_t next_random(void) {
    g_random ^= g_random << 13;
    g_random ^= g_random >> 17;
    g_random ^= g_random << 5;
    return g_random;
}

static void put_u32le(uint8_t *p, uint32_t v) {
    p[0] = (uint8_t)(v & UINT32_C(0xff));
    p[1] = (uint8_t)((v >> 8) & UINT32_C(0xff));
    p[2] = (uint8_t)((v >> 16) & UINT32_C(0xff));
    p[3] = (uint8_t)((v >> 24) & UINT32_C(0xff));
}

int main(void) {
    uint8_t bytes[512];
    char error[128];
    for (size_t iteration = 0; iteration < 30000U; ++iteration) {
        const size_t length = (size_t)(next_random() % (uint32_t)sizeof(bytes)) + 1U;
        for (size_t i = 0U; i < length; ++i) {
            bytes[i] = (uint8_t)(next_random() & UINT32_C(0xff));
        }
        /* Force a share of cases past the magic/flag checks and into block parsing. */
        if ((iteration % 2U) == 0U && length >= 8U) {
            put_u32le(bytes, UINT32_C(0x10));
            put_u32le(bytes + 4U, next_random() & UINT32_C(0x0f));
        }
        if ((iteration % 7U) == 0U && length >= 20U) {
            put_u32le(bytes, UINT32_C(0x10));
            put_u32le(bytes + 4U, next_random() & UINT32_C(0x0f));
            put_u32le(bytes + 8U, next_random());
        }

        TimImage image;
        (void)memset(&image, 0xa5, sizeof(image));
        (void)memset(error, 0, sizeof(error));
        const int status = tim_image_decode_rgba(bytes, length, &image, error, sizeof(error));
        if (status == 0) {
            assert(image.width > 0U && image.height > 0U);
            assert(image.rgba != NULL);
            assert(image.rgba_size == (size_t)image.width * (size_t)image.height * 4U);
            tim_image_free(&image);
        } else {
            assert(image.width == 0U && image.height == 0U);
            assert(image.rgba == NULL && image.clut_words == NULL);
            assert(image.rgba_size == 0U && image.clut_entries == 0U);
        }
    }
    return 0;
}
