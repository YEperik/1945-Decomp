#include "tim_image.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define TIM_HEADER_BYTES ((size_t)8)
#define TIM_BLOCK_HEADER_BYTES ((size_t)12)
#define TIM_FLAG_CLUT UINT32_C(0x08)
#define TIM_FLAG_ALLOWED UINT32_C(0x0f)
#define TIM_MODE_4BPP UINT32_C(0)
#define TIM_MODE_8BPP UINT32_C(1)
#define TIM_MODE_16BPP UINT32_C(2)
#define TIM_MODE_24BPP UINT32_C(3)

static uint16_t read_u16_le(const uint8_t *p) {
    return (uint16_t)((uint16_t)p[0] | ((uint16_t)p[1] << 8));
}

static uint32_t read_u32_le(const uint8_t *p) {
    return (uint32_t)p[0] |
           ((uint32_t)p[1] << 8) |
           ((uint32_t)p[2] << 16) |
           ((uint32_t)p[3] << 24);
}

static void set_error(char *error, size_t capacity, const char *message) {
    if (error != NULL && capacity > 0U) {
        (void)snprintf(error, capacity, "%s", message);
    }
}

static int multiply_size(size_t a, size_t b, size_t *result) {
    if (result == NULL || (b != 0U && a > SIZE_MAX / b)) {
        return -1;
    }
    *result = a * b;
    return 0;
}

static int block_size_matches(uint32_t declared, size_t payload_size) {
    if (payload_size > SIZE_MAX - TIM_BLOCK_HEADER_BYTES) {
        return 0;
    }
    return ((size_t)declared == payload_size) ||
           ((size_t)declared == payload_size + TIM_BLOCK_HEADER_BYTES);
}

static uint8_t expand_5_to_8(uint16_t value) {
    const uint16_t five = (uint16_t)(value & UINT16_C(0x1f));
    return (uint8_t)((five << 3) | (five >> 2));
}

static void color_5551_to_rgba(uint16_t color, uint8_t *rgba) {
    rgba[0] = expand_5_to_8(color);
    rgba[1] = expand_5_to_8((uint16_t)(color >> 5));
    rgba[2] = expand_5_to_8((uint16_t)(color >> 10));
    if (color == 0U) {
        rgba[3] = 0U;
    } else if ((color & UINT16_C(0x8000)) != 0U) {
        /* PSX STP is represented as half alpha by this RGBA preview path. */
        rgba[3] = 128U;
    } else {
        rgba[3] = 255U;
    }
}

void tim_image_free(TimImage *image) {
    if (image == NULL) {
        return;
    }
    free(image->clut_words);
    free(image->rgba);
    (void)memset(image, 0, sizeof(*image));
}

int tim_image_decode_rgba(const uint8_t *data,
                          size_t size,
                          TimImage *out,
                          char *error,
                          size_t error_capacity) {
    TimImage decoded;
    uint32_t flags;
    uint32_t mode;
    size_t cursor;
    size_t raw_row_bytes;
    size_t payload_size;
    size_t pixel_count;
    size_t rgba_size;
    size_t image_data_offset;
    uint32_t width;
    uint32_t height;
    uint32_t word_width;
    uint32_t clut_width = 0U;
    uint32_t clut_height = 0U;
    size_t clut_payload_size = 0U;
    size_t clut_data_offset = 0U;
    size_t required_palette_entries = 0U;
    uint32_t x;
    uint32_t y;
    size_t i;

    (void)memset(&decoded, 0, sizeof(decoded));
    if (error != NULL && error_capacity > 0U) {
        error[0] = '\0';
    }
    if (out == NULL) {
        set_error(error, error_capacity, "output pointer is null");
        return -1;
    }
    (void)memset(out, 0, sizeof(*out));
    if (data == NULL || size < TIM_HEADER_BYTES) {
        set_error(error, error_capacity, "TIM header is truncated");
        return -1;
    }
    if (read_u32_le(data) != UINT32_C(0x10)) {
        set_error(error, error_capacity, "invalid TIM magic");
        return -1;
    }

    flags = read_u32_le(data + 4U);
    if ((flags & ~TIM_FLAG_ALLOWED) != 0U) {
        set_error(error, error_capacity, "unsupported TIM flag bits");
        return -1;
    }
    mode = flags & UINT32_C(0x07);
    if (mode > TIM_MODE_24BPP) {
        set_error(error, error_capacity, "unsupported TIM pixel mode");
        return -1;
    }
    decoded.pixel_mode = mode;
    decoded.has_clut = (uint8_t)((flags & TIM_FLAG_CLUT) != 0U ? 1U : 0U);
    if (decoded.has_clut != 0U && mode >= TIM_MODE_16BPP) {
        set_error(error, error_capacity, "CLUT is not valid for direct-color TIM mode");
        return -1;
    }

    cursor = TIM_HEADER_BYTES;
    if (decoded.has_clut != 0U) {
        uint32_t declared_size;
        size_t entries;
        if (size - cursor < TIM_BLOCK_HEADER_BYTES) {
            set_error(error, error_capacity, "CLUT block header is truncated");
            goto fail;
        }
        declared_size = read_u32_le(data + cursor);
        decoded.clut_x = (uint32_t)read_u16_le(data + cursor + 4U);
        decoded.clut_y = (uint32_t)read_u16_le(data + cursor + 6U);
        clut_width = (uint32_t)read_u16_le(data + cursor + 8U);
        clut_height = (uint32_t)read_u16_le(data + cursor + 10U);
        if (clut_width == 0U || clut_height == 0U) {
            set_error(error, error_capacity, "CLUT dimensions are zero");
            goto fail;
        }
        if (multiply_size((size_t)clut_width, (size_t)clut_height, &entries) != 0 ||
            multiply_size(entries, sizeof(uint16_t), &clut_payload_size) != 0) {
            set_error(error, error_capacity, "CLUT size overflows address space");
            goto fail;
        }
        if (!block_size_matches(declared_size, clut_payload_size)) {
            set_error(error, error_capacity, "CLUT block length disagrees with dimensions");
            goto fail;
        }
        if (clut_payload_size > size - cursor - TIM_BLOCK_HEADER_BYTES) {
            set_error(error, error_capacity, "CLUT payload is truncated");
            goto fail;
        }
        clut_data_offset = cursor + TIM_BLOCK_HEADER_BYTES;
        decoded.clut_width = clut_width;
        decoded.clut_height = clut_height;
        decoded.clut_entries = entries;
        decoded.clut_words = (uint16_t *)malloc(clut_payload_size);
        if (decoded.clut_words == NULL) {
            set_error(error, error_capacity, "CLUT allocation failed");
            goto fail;
        }
        for (i = 0U; i < entries; ++i) {
            decoded.clut_words[i] = read_u16_le(data + clut_data_offset + i * 2U);
        }
        cursor += TIM_BLOCK_HEADER_BYTES + clut_payload_size;
    }

    if (size - cursor < TIM_BLOCK_HEADER_BYTES) {
        set_error(error, error_capacity, "image block header is truncated");
        goto fail;
    }
    {
        uint32_t declared_size = read_u32_le(data + cursor);
        decoded.image_x = (uint32_t)read_u16_le(data + cursor + 4U);
        decoded.image_y = (uint32_t)read_u16_le(data + cursor + 6U);
        word_width = (uint32_t)read_u16_le(data + cursor + 8U);
        height = (uint32_t)read_u16_le(data + cursor + 10U);
        if (word_width == 0U || height == 0U) {
            set_error(error, error_capacity, "image dimensions are zero");
            goto fail;
        }
        /* word_width is read from a 16-bit TIM field, so doubling is bounded. */
        raw_row_bytes = (size_t)word_width * 2U;
        if (multiply_size(raw_row_bytes, (size_t)height, &payload_size) != 0) {
            set_error(error, error_capacity, "image payload size overflows address space");
            goto fail;
        }
        if (!block_size_matches(declared_size, payload_size)) {
            set_error(error, error_capacity, "image block length disagrees with dimensions");
            goto fail;
        }
        image_data_offset = cursor + TIM_BLOCK_HEADER_BYTES;
        if (image_data_offset > size || payload_size != size - image_data_offset) {
            set_error(error, error_capacity, "image payload length does not match file size");
            goto fail;
        }
    }

    if (mode == TIM_MODE_4BPP) {
        if (word_width > UINT32_MAX / 4U) {
            set_error(error, error_capacity, "4bpp pixel width overflows");
            goto fail;
        }
        width = word_width * 4U;
        required_palette_entries = 16U;
    } else if (mode == TIM_MODE_8BPP) {
        if (word_width > UINT32_MAX / 2U) {
            set_error(error, error_capacity, "8bpp pixel width overflows");
            goto fail;
        }
        width = word_width * 2U;
        required_palette_entries = 256U;
    } else if (mode == TIM_MODE_16BPP) {
        width = word_width;
    } else {
        if (raw_row_bytes % 3U != 0U) {
            set_error(error, error_capacity, "24bpp row byte count is not divisible by three");
            goto fail;
        }
        width = (uint32_t)(raw_row_bytes / 3U);
    }
    if (width == 0U || height == 0U) {
        set_error(error, error_capacity, "decoded image dimensions are zero");
        goto fail;
    }
    if (required_palette_entries > 0U) {
        if (decoded.has_clut == 0U || clut_width < required_palette_entries ||
            decoded.clut_entries < required_palette_entries) {
            set_error(error, error_capacity, "indexed TIM does not contain a complete first palette");
            goto fail;
        }
    }
    if (multiply_size((size_t)width, (size_t)height, &pixel_count) != 0 ||
        multiply_size(pixel_count, 4U, &rgba_size) != 0) {
        set_error(error, error_capacity, "RGBA output size overflows address space");
        goto fail;
    }
    decoded.rgba = (uint8_t *)malloc(rgba_size);
    if (decoded.rgba == NULL) {
        set_error(error, error_capacity, "RGBA allocation failed");
        goto fail;
    }
    decoded.width = width;
    decoded.height = height;
    decoded.rgba_size = rgba_size;

    for (y = 0U; y < height; ++y) {
        const uint8_t *row = data + image_data_offset + (size_t)y * raw_row_bytes;
        for (x = 0U; x < width; ++x) {
            uint8_t *dst = decoded.rgba + (((size_t)y * width + x) * 4U);
            if (mode == TIM_MODE_4BPP) {
                const uint8_t packed = row[x / 2U];
                const size_t palette_index = (size_t)((x & 1U) != 0U ? packed >> 4 : packed & 0x0fU);
                color_5551_to_rgba(decoded.clut_words[palette_index], dst);
            } else if (mode == TIM_MODE_8BPP) {
                const size_t palette_index = (size_t)row[x];
                color_5551_to_rgba(decoded.clut_words[palette_index], dst);
            } else if (mode == TIM_MODE_16BPP) {
                color_5551_to_rgba(read_u16_le(row + (size_t)x * 2U), dst);
            } else {
                dst[0] = row[(size_t)x * 3U];
                dst[1] = row[(size_t)x * 3U + 1U];
                dst[2] = row[(size_t)x * 3U + 2U];
                dst[3] = 255U;
            }
        }
    }

    *out = decoded;
    return 0;

fail:
    tim_image_free(&decoded);
    return -1;
}
