#include "tim_texture_renderer.h"

#include <GLES2/gl2.h>
#include <android/log.h>

#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>

namespace {
constexpr const char *kLogTag = "1945TimTexture";
constexpr std::size_t kMaxCacheEntries = 4096u;
constexpr std::size_t kMaxStaleGlErrorsToDrain = 8u;
constexpr uint64_t kFnvOffset = UINT64_C(14695981039346656037);
constexpr uint64_t kFnvPrime = UINT64_C(1099511628211);

struct TextureEntry {
    uint32_t key;
    GLuint texture;
    uint32_t width;
    uint32_t height;
    size_t bytes;
    uint64_t hash;
};

struct SpriteVertex {
    GLfloat x;
    GLfloat y;
    GLfloat u;
    GLfloat v;
};

GLuint g_sprite_program = 0u;
GLint g_sprite_position = -1;
GLint g_sprite_uv = -1;
GLint g_sprite_resolution = -1;
GLint g_sprite_tint = -1;
GLint g_sprite_sampler = -1;

void set_error(char *error, size_t capacity, const char *message)
{
    if (error != nullptr && capacity > 0u) {
        (void)std::snprintf(error, capacity, "%s", message);
    }
}

bool multiply_size(size_t a, size_t b, size_t *result)
{
    if (result == nullptr || (b != 0u && a > std::numeric_limits<size_t>::max() / b)) {
        return false;
    }
    *result = a * b;
    return true;
}

uint64_t hash_rgba(const uint8_t *data, size_t size)
{
    uint64_t hash = kFnvOffset;
    for (size_t i = 0u; i < size; ++i) {
        hash ^= static_cast<uint64_t>(data[i]);
        hash *= kFnvPrime;
    }
    return hash;
}

TextureEntry *entries(TimTextureCache *cache)
{
    return cache == nullptr ? nullptr : static_cast<TextureEntry *>(cache->entries);
}

const TextureEntry *entries(const TimTextureCache *cache)
{
    return cache == nullptr ? nullptr : static_cast<const TextureEntry *>(cache->entries);
}

void drain_gl_errors()
{
    for (size_t i = 0u; i < kMaxStaleGlErrorsToDrain; ++i) {
        if (glGetError() == GL_NO_ERROR) {
            break;
        }
    }
}

GLuint compile_shader(GLenum type, const char *source, char *error, size_t error_capacity)
{
    const GLuint shader = glCreateShader(type);
    if (shader == 0u) {
        set_error(error, error_capacity, "glCreateShader returned zero");
        return 0u;
    }
    glShaderSource(shader, 1, &source, nullptr);
    glCompileShader(shader);
    GLint compiled = GL_FALSE;
    glGetShaderiv(shader, GL_COMPILE_STATUS, &compiled);
    if (compiled != GL_TRUE) {
        GLint log_length = 0;
        glGetShaderiv(shader, GL_INFO_LOG_LENGTH, &log_length);
        if (log_length > 1) {
            char log_buffer[512] = {};
            GLsizei written = 0;
            glGetShaderInfoLog(shader, static_cast<GLsizei>(sizeof(log_buffer)), &written, log_buffer);
            __android_log_print(ANDROID_LOG_ERROR, kLogTag, "Sprite shader compile failed: %s", log_buffer);
        }
        glDeleteShader(shader);
        set_error(error, error_capacity, "sprite shader compilation failed");
        return 0u;
    }
    return shader;
}

void reset_sprite_handles()
{
    /* Surface-created indicates a new EGL context; old names are not deletable here. */
    g_sprite_program = 0u;
    g_sprite_position = -1;
    g_sprite_uv = -1;
    g_sprite_resolution = -1;
    g_sprite_tint = -1;
    g_sprite_sampler = -1;
}
} // namespace

extern "C" int tim_texture_cache_init(TimTextureCache *cache,
                                        size_t max_textures,
                                        size_t max_bytes,
                                        char *error,
                                        size_t error_capacity)
{
    if (error != nullptr && error_capacity > 0u) error[0] = '\0';
    if (cache == nullptr) {
        set_error(error, error_capacity, "cache pointer is null");
        return -1;
    }
    if (cache->entries != nullptr) {
        set_error(error, error_capacity, "cache must be zero-initialized or destroyed first");
        return -1;
    }
    if (max_textures == 0u || max_textures > kMaxCacheEntries || max_bytes == 0u) {
        set_error(error, error_capacity, "cache limits are outside supported bounds");
        return -1;
    }
    size_t allocation_size = 0u;
    if (!multiply_size(max_textures, sizeof(TextureEntry), &allocation_size)) {
        set_error(error, error_capacity, "cache allocation size overflows");
        return -1;
    }
    TextureEntry *allocated = static_cast<TextureEntry *>(std::calloc(1u, allocation_size));
    if (allocated == nullptr) {
        set_error(error, error_capacity, "cache allocation failed");
        return -1;
    }
    cache->entries = allocated;
    cache->count = 0u;
    cache->capacity = max_textures;
    cache->used_bytes = 0u;
    cache->max_bytes = max_bytes;
    return 0;
}

extern "C" int tim_texture_cache_upload_rgba(TimTextureCache *cache,
                                               uint32_t key,
                                               uint32_t width,
                                               uint32_t height,
                                               const uint8_t *rgba,
                                               size_t rgba_size,
                                               uint32_t *texture_out,
                                               char *error,
                                               size_t error_capacity)
{
    if (error != nullptr && error_capacity > 0u) error[0] = '\0';
    if (texture_out != nullptr) *texture_out = 0u;
    if (cache == nullptr || cache->entries == nullptr || texture_out == nullptr || rgba == nullptr) {
        set_error(error, error_capacity, "cache, pixels, or output pointer is invalid");
        return -1;
    }
    if (width == 0u || height == 0u ||
        width > static_cast<uint32_t>(std::numeric_limits<GLsizei>::max()) ||
        height > static_cast<uint32_t>(std::numeric_limits<GLsizei>::max())) {
        set_error(error, error_capacity, "texture dimensions are invalid");
        return -1;
    }
    size_t pixel_count = 0u;
    size_t expected_bytes = 0u;
    if (!multiply_size(static_cast<size_t>(width), static_cast<size_t>(height), &pixel_count) ||
        !multiply_size(pixel_count, 4u, &expected_bytes) || expected_bytes != rgba_size) {
        set_error(error, error_capacity, "RGBA byte count does not match dimensions");
        return -1;
    }
    const uint64_t hash = hash_rgba(rgba, rgba_size);
    TextureEntry *items = entries(cache);
    for (size_t i = 0u; i < cache->count; ++i) {
        if (items[i].key == key) {
            if (items[i].width == width && items[i].height == height &&
                items[i].bytes == expected_bytes && items[i].hash == hash) {
                *texture_out = static_cast<uint32_t>(items[i].texture);
                return 0;
            }
            set_error(error, error_capacity, "texture key already refers to different pixel content");
            return -1;
        }
    }
    if (cache->count >= cache->capacity) {
        set_error(error, error_capacity, "texture cache entry capacity exceeded");
        return -1;
    }
    if (expected_bytes > cache->max_bytes || cache->used_bytes > cache->max_bytes - expected_bytes) {
        set_error(error, error_capacity, "texture cache byte budget exceeded");
        return -1;
    }

    drain_gl_errors();
    GLint previous_texture_binding = 0;
    GLint previous_unpack_alignment = 4;
    glGetIntegerv(GL_TEXTURE_BINDING_2D, &previous_texture_binding);
    glGetIntegerv(GL_UNPACK_ALIGNMENT, &previous_unpack_alignment);
    GLuint texture = 0u;
    glGenTextures(1, &texture);
    if (texture == 0u) {
        set_error(error, error_capacity, "glGenTextures returned zero");
        return -1;
    }
    glBindTexture(GL_TEXTURE_2D, texture);
    glPixelStorei(GL_UNPACK_ALIGNMENT, 1);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, static_cast<GLsizei>(width),
                 static_cast<GLsizei>(height), 0, GL_RGBA, GL_UNSIGNED_BYTE, rgba);
    const GLenum upload_error = glGetError();
    glBindTexture(GL_TEXTURE_2D, static_cast<GLuint>(previous_texture_binding));
    glPixelStorei(GL_UNPACK_ALIGNMENT, previous_unpack_alignment);
    if (upload_error != GL_NO_ERROR) {
        glDeleteTextures(1, &texture);
        set_error(error, error_capacity, "GLES rejected texture upload");
        return -1;
    }

    TextureEntry &entry = items[cache->count++];
    entry.key = key;
    entry.texture = texture;
    entry.width = width;
    entry.height = height;
    entry.bytes = expected_bytes;
    entry.hash = hash;
    cache->used_bytes += expected_bytes;
    *texture_out = static_cast<uint32_t>(texture);
    return 0;
}

extern "C" int tim_texture_cache_lookup(const TimTextureCache *cache,
                                          uint32_t key,
                                          uint32_t *texture_out)
{
    if (texture_out != nullptr) *texture_out = 0u;
    if (cache == nullptr || cache->entries == nullptr || texture_out == nullptr) return -1;
    const TextureEntry *items = entries(cache);
    for (size_t i = 0u; i < cache->count; ++i) {
        if (items[i].key == key) {
            *texture_out = static_cast<uint32_t>(items[i].texture);
            return items[i].texture == 0u ? -1 : 0;
        }
    }
    return -1;
}

extern "C" void tim_texture_cache_context_lost(TimTextureCache *cache)
{
    if (cache == nullptr || cache->entries == nullptr) return;
    TextureEntry *items = entries(cache);
    for (size_t i = 0u; i < cache->count; ++i) {
        items[i].texture = 0u;
    }
    cache->count = 0u;
    cache->used_bytes = 0u;
}

extern "C" void tim_texture_cache_destroy(TimTextureCache *cache)
{
    if (cache == nullptr) return;
    TextureEntry *items = entries(cache);
    if (items != nullptr) {
        for (size_t i = 0u; i < cache->count; ++i) {
            if (items[i].texture != 0u) {
                const GLuint texture = items[i].texture;
                glDeleteTextures(1, &texture);
            }
        }
        std::free(items);
    }
    (void)std::memset(cache, 0, sizeof(*cache));
}

extern "C" int tim_sprite_renderer_surface_created(char *error, size_t error_capacity)
{
    if (error != nullptr && error_capacity > 0u) error[0] = '\0';
    reset_sprite_handles();
    static const char *vertex_source =
        "attribute vec2 a_position;\n"
        "attribute vec2 a_uv;\n"
        "uniform vec2 u_resolution;\n"
        "varying vec2 v_uv;\n"
        "void main() {\n"
        "  vec2 clip = (a_position / u_resolution) * 2.0 - 1.0;\n"
        "  gl_Position = vec4(clip.x, -clip.y, 0.0, 1.0);\n"
        "  v_uv = a_uv;\n"
        "}\n";
    static const char *fragment_source =
        "precision mediump float;\n"
        "uniform sampler2D u_texture;\n"
        "uniform vec4 u_tint;\n"
        "varying vec2 v_uv;\n"
        "void main() { gl_FragColor = texture2D(u_texture, v_uv) * u_tint; }\n";
    const GLuint vertex_shader = compile_shader(GL_VERTEX_SHADER, vertex_source, error, error_capacity);
    const GLuint fragment_shader = compile_shader(GL_FRAGMENT_SHADER, fragment_source, error, error_capacity);
    if (vertex_shader == 0u || fragment_shader == 0u) {
        if (vertex_shader != 0u) glDeleteShader(vertex_shader);
        if (fragment_shader != 0u) glDeleteShader(fragment_shader);
        return -1;
    }
    const GLuint program = glCreateProgram();
    if (program == 0u) {
        glDeleteShader(vertex_shader);
        glDeleteShader(fragment_shader);
        set_error(error, error_capacity, "glCreateProgram returned zero");
        return -1;
    }
    glAttachShader(program, vertex_shader);
    glAttachShader(program, fragment_shader);
    glBindAttribLocation(program, 0u, "a_position");
    glBindAttribLocation(program, 1u, "a_uv");
    glLinkProgram(program);
    glDeleteShader(vertex_shader);
    glDeleteShader(fragment_shader);
    GLint linked = GL_FALSE;
    glGetProgramiv(program, GL_LINK_STATUS, &linked);
    if (linked != GL_TRUE) {
        glDeleteProgram(program);
        set_error(error, error_capacity, "sprite program link failed");
        return -1;
    }
    const GLint position = glGetAttribLocation(program, "a_position");
    const GLint uv = glGetAttribLocation(program, "a_uv");
    const GLint resolution = glGetUniformLocation(program, "u_resolution");
    const GLint tint = glGetUniformLocation(program, "u_tint");
    const GLint sampler = glGetUniformLocation(program, "u_texture");
    if (position < 0 || uv < 0 || resolution < 0 || tint < 0 || sampler < 0) {
        glDeleteProgram(program);
        set_error(error, error_capacity, "required sprite shader location is missing");
        return -1;
    }
    g_sprite_program = program;
    g_sprite_position = position;
    g_sprite_uv = uv;
    g_sprite_resolution = resolution;
    g_sprite_tint = tint;
    g_sprite_sampler = sampler;
    glDisable(GL_DEPTH_TEST);
    glEnable(GL_BLEND);
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
    return 0;
}

extern "C" int tim_sprite_renderer_draw(uint32_t texture,
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
                                          float tint_a)
{
    if (g_sprite_program == 0u || texture == 0u || texture_width == 0u || texture_height == 0u ||
        src_width == 0u || src_height == 0u || src_x > texture_width || src_y > texture_height ||
        src_width > texture_width - src_x || src_height > texture_height - src_y ||
        !std::isfinite(logical_width) || !std::isfinite(logical_height) ||
        !std::isfinite(dst_x) || !std::isfinite(dst_y) ||
        !std::isfinite(dst_width) || !std::isfinite(dst_height) ||
        !std::isfinite(tint_r) || !std::isfinite(tint_g) || !std::isfinite(tint_b) || !std::isfinite(tint_a) ||
        logical_width <= 0.0f || logical_height <= 0.0f || dst_width <= 0.0f || dst_height <= 0.0f) {
        return -1;
    }
    const GLfloat u0 = static_cast<GLfloat>(src_x) / static_cast<GLfloat>(texture_width);
    const GLfloat v0 = static_cast<GLfloat>(src_y) / static_cast<GLfloat>(texture_height);
    const GLfloat u1 = static_cast<GLfloat>(src_x + src_width) / static_cast<GLfloat>(texture_width);
    const GLfloat v1 = static_cast<GLfloat>(src_y + src_height) / static_cast<GLfloat>(texture_height);
    const GLfloat x0 = dst_x;
    const GLfloat y0 = dst_y;
    const GLfloat x1 = dst_x + dst_width;
    const GLfloat y1 = dst_y + dst_height;
    if (!std::isfinite(x1) || !std::isfinite(y1)) return -1;
    const SpriteVertex vertices[6] = {
        {x0, y0, u0, v0}, {x1, y0, u1, v0}, {x1, y1, u1, v1},
        {x0, y0, u0, v0}, {x1, y1, u1, v1}, {x0, y1, u0, v1}
    };

    glUseProgram(g_sprite_program);
    glUniform2f(g_sprite_resolution, logical_width, logical_height);
    glUniform4f(g_sprite_tint, tint_r, tint_g, tint_b, tint_a);
    glUniform1i(g_sprite_sampler, 0);
    glActiveTexture(GL_TEXTURE0);
    glBindTexture(GL_TEXTURE_2D, static_cast<GLuint>(texture));
    glBindBuffer(GL_ARRAY_BUFFER, 0u);
    glEnableVertexAttribArray(static_cast<GLuint>(g_sprite_position));
    glEnableVertexAttribArray(static_cast<GLuint>(g_sprite_uv));
    glVertexAttribPointer(static_cast<GLuint>(g_sprite_position), 2, GL_FLOAT, GL_FALSE,
                          static_cast<GLsizei>(sizeof(SpriteVertex)),
                          static_cast<const void *>(&vertices[0].x));
    glVertexAttribPointer(static_cast<GLuint>(g_sprite_uv), 2, GL_FLOAT, GL_FALSE,
                          static_cast<GLsizei>(sizeof(SpriteVertex)),
                          static_cast<const void *>(&vertices[0].u));
    glDrawArrays(GL_TRIANGLES, 0, 6);
    glDisableVertexAttribArray(static_cast<GLuint>(g_sprite_position));
    glDisableVertexAttribArray(static_cast<GLuint>(g_sprite_uv));
    glBindTexture(GL_TEXTURE_2D, 0u);
    glUseProgram(0u);
    return 0;
}
