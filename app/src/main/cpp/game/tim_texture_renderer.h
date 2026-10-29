#ifndef PORT1945_TIM_TEXTURE_RENDERER_H
#define PORT1945_TIM_TEXTURE_RENDERER_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct TimTextureCache {
    void *entries;
    size_t count;
    size_t capacity;
    size_t used_bytes;
    size_t max_bytes;
} TimTextureCache;

/*
 * Initialize a bounded texture cache. max_textures must be in [1, 4096],
 * and max_bytes must be non-zero. The cache owns its bookkeeping allocation.
 */
int tim_texture_cache_init(TimTextureCache *cache,
                           size_t max_textures,
                           size_t max_bytes,
                           char *error,
                           size_t error_capacity);

/* Upload tightly packed RGBA8 pixels. Reusing a key requires identical content. */
int tim_texture_cache_upload_rgba(TimTextureCache *cache,
                                  uint32_t key,
                                  uint32_t width,
                                  uint32_t height,
                                  const uint8_t *rgba,
                                  size_t rgba_size,
                                  uint32_t *texture_out,
                                  char *error,
                                  size_t error_capacity);

int tim_texture_cache_lookup(const TimTextureCache *cache,
                             uint32_t key,
                             uint32_t *texture_out);

/* Call when the EGL context has been lost/replaced. Makes no GL calls. */
void tim_texture_cache_context_lost(TimTextureCache *cache);

/* Call only while the context owning the cached GL names is current. */
void tim_texture_cache_destroy(TimTextureCache *cache);

/* Create/recreate the independent GLES2 sprite draw program for current context. */
int tim_sprite_renderer_surface_created(char *error, size_t error_capacity);

/* Draw an RGBA texture sub-rectangle into a top-left-origin logical viewport.
 * Source rectangles are in pixels; destination coordinates are logical units.
 * Returns 0 on submission, -1 for invalid input or unavailable GL resources.
 */
int tim_sprite_renderer_draw(uint32_t texture,
                             uint32_t texture_width,
                             uint32_t texture_height,
                             float logical_width,
                             float logical_height,
                             float dst_x,
                             float dst_y,
                             float dst_width,
                             float dst_height,
                             uint32_t src_x,
                             uint32_t src_y,
                             uint32_t src_width,
                             uint32_t src_height,
                             float tint_r,
                             float tint_g,
                             float tint_b,
                             float tint_a);

#ifdef __cplusplus
}
#endif

#endif /* PORT1945_TIM_TEXTURE_RENDERER_H */
