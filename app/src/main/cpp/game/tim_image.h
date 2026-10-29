#ifndef PORT1945_TIM_IMAGE_H
#define PORT1945_TIM_IMAGE_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct TimImage {
    uint32_t image_x;
    uint32_t image_y;
    uint32_t width;
    uint32_t height;
    uint32_t pixel_mode;
    uint8_t has_clut;

    uint32_t clut_x;
    uint32_t clut_y;
    uint32_t clut_width;
    uint32_t clut_height;
    size_t clut_entries;
    uint16_t *clut_words;

    uint8_t *rgba;
    size_t rgba_size;
} TimImage;

/*
 * Decode a bounded PlayStation TIM image into tightly packed RGBA8.
 *
 * Supported pixel modes are 4-bit indexed, 8-bit indexed, direct 16-bit,
 * and direct 24-bit. Indexed images use the first CLUT row for the returned
 * preview; the full CLUT is retained in clut_words for later palette mapping.
 * A TIM image block may declare either its complete size (header + payload)
 * or the payload size alone; both forms occur in the supplied disc image.
 *
 * Returns 0 on success and -1 on malformed/unsupported input or allocation
 * failure. On failure, out is zeroed and error receives a short diagnostic
 * when a non-null, non-empty error buffer is supplied.
 */
int tim_image_decode_rgba(const uint8_t *data,
                          size_t size,
                          TimImage *out,
                          char *error,
                          size_t error_capacity);

void tim_image_free(TimImage *image);

#ifdef __cplusplus
}
#endif

#endif /* PORT1945_TIM_IMAGE_H */
