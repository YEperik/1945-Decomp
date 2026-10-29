"""Host-mock tests for bounded GLES TIM texture upload and sprite drawing."""
from __future__ import annotations

import pathlib
import shutil
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
GAME_DIR = ROOT / "app/src/main/cpp/game"
STUB_DIR = ROOT / "tests/native_stubs"

HARNESS = r'''#include <cassert>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <cstdio>
#include "GLES2/gl2.h"
#include "tim_texture_renderer.h"
#include "android/log.h"

static GLuint next_name = 1u;
static bool compile_ok = true;
static bool link_ok = true;
static bool locations_ok = true;
static bool fail_gen = false;
static bool fail_upload = false;
static int tex_image_calls = 0;
static int texture_delete_calls = 0;
static int program_delete_calls = 0;
static int draw_calls = 0;
static int active_texture_calls = 0;
static std::size_t uploaded_size = 0u;
static GLsizei uploaded_width = 0;
static GLsizei uploaded_height = 0;
static GLenum pending_error = GL_NO_ERROR;
static GLint bound_texture = 0;
static GLint unpack_alignment = 4;
static const unsigned char *last_upload_pixels = nullptr;
static GLfloat captured_vertices[6][4] = {};
static std::size_t position_stride = 0u;
static std::size_t uv_stride = 0u;
static const unsigned char *position_pointer = nullptr;
static const unsigned char *uv_pointer = nullptr;
static bool position_enabled = false;
static bool uv_enabled = false;

GLuint glCreateShader(GLenum) { return next_name++; }
void glShaderSource(GLuint, GLsizei, const GLchar *const *, const GLint *) {}
void glCompileShader(GLuint) {}
void glGetShaderiv(GLuint, GLenum pname, GLint *params) {
    if (pname == GL_COMPILE_STATUS) *params = compile_ok ? GL_TRUE : GL_FALSE;
    else if (pname == GL_INFO_LOG_LENGTH) *params = compile_ok ? 0 : 8;
    else *params = 0;
}
void glGetShaderInfoLog(GLuint, GLsizei, GLsizei *length, GLchar *buffer) {
    if (length != nullptr) *length = 0;
    if (buffer != nullptr) buffer[0] = '\0';
}
void glDeleteShader(GLuint) {}
void glDeleteBuffers(GLsizei, const GLuint *) {}
void glDeleteProgram(GLuint) { ++program_delete_calls; }
GLuint glCreateProgram(void) { return next_name++; }
void glAttachShader(GLuint, GLuint) {}
void glBindAttribLocation(GLuint, GLuint, const GLchar *) {}
void glLinkProgram(GLuint) {}
void glGetProgramiv(GLuint, GLenum pname, GLint *params) {
    if (pname == GL_LINK_STATUS) *params = link_ok ? GL_TRUE : GL_FALSE;
    else if (pname == GL_INFO_LOG_LENGTH) *params = link_ok ? 0 : 8;
    else *params = 0;
}
void glGetProgramInfoLog(GLuint, GLsizei, GLsizei *length, GLchar *buffer) {
    if (length != nullptr) *length = 0;
    if (buffer != nullptr) buffer[0] = '\0';
}
GLint glGetAttribLocation(GLuint, const GLchar *name) {
    if (!locations_ok) return -1;
    if (std::strcmp(name, "a_position") == 0) return 0;
    if (std::strcmp(name, "a_uv") == 0) return 1;
    return -1;
}
GLint glGetUniformLocation(GLuint, const GLchar *name) {
    if (!locations_ok) return -1;
    if (std::strcmp(name, "u_resolution") == 0) return 2;
    if (std::strcmp(name, "u_tint") == 0) return 3;
    if (std::strcmp(name, "u_texture") == 0) return 4;
    return -1;
}
void glGenBuffers(GLsizei, GLuint *) {}
void glBindBuffer(GLenum, GLuint) {}
void glBufferData(GLenum, GLsizeiptr, const void *, GLenum) {}
void glDisable(GLenum) {}
void glEnable(GLenum) {}
void glBlendFunc(GLenum, GLenum) {}
void glViewport(GLint, GLint, GLsizei, GLsizei) {}
void glClearColor(GLfloat, GLfloat, GLfloat, GLfloat) {}
void glClear(GLenum) {}
void glUseProgram(GLuint) {}
void glUniform2f(GLint, GLfloat, GLfloat) {}
void glUniform4f(GLint, GLfloat, GLfloat, GLfloat, GLfloat) {}
void glUniform1i(GLint, GLint) {}
void glBufferSubData(GLenum, GLintptr, GLsizeiptr, const void *) {}
void glEnableVertexAttribArray(GLuint index) {
    if (index == 0u) position_enabled = true;
    if (index == 1u) uv_enabled = true;
}
void glVertexAttribPointer(GLuint index, GLint, GLenum, GLboolean, GLsizei stride, const void *pointer) {
    if (index == 0u) {
        position_pointer = static_cast<const unsigned char *>(pointer);
        position_stride = static_cast<std::size_t>(stride);
    } else if (index == 1u) {
        uv_pointer = static_cast<const unsigned char *>(pointer);
        uv_stride = static_cast<std::size_t>(stride);
    }
}
void glDrawArrays(GLenum mode, GLint first, GLsizei count) {
    assert(mode == GL_TRIANGLES && first == 0 && count == 6);
    assert(position_pointer != nullptr && uv_pointer != nullptr);
    assert(position_stride == 4u * sizeof(GLfloat) && uv_stride == position_stride);
    for (std::size_t i = 0u; i < 6u; ++i) {
        const GLfloat *position = reinterpret_cast<const GLfloat *>(position_pointer + i * position_stride);
        const GLfloat *uv = reinterpret_cast<const GLfloat *>(uv_pointer + i * uv_stride);
        captured_vertices[i][0] = position[0];
        captured_vertices[i][1] = position[1];
        captured_vertices[i][2] = uv[0];
        captured_vertices[i][3] = uv[1];
    }
    ++draw_calls;
}
void glDisableVertexAttribArray(GLuint index) {
    if (index == 0u) position_enabled = false;
    if (index == 1u) uv_enabled = false;
}
void glGenTextures(GLsizei n, GLuint *textures) {
    for (GLsizei i = 0; i < n; ++i) textures[i] = fail_gen ? 0u : next_name++;
}
void glDeleteTextures(GLsizei n, const GLuint *) { texture_delete_calls += n; }
void glBindTexture(GLenum target, GLuint texture) {
    assert(target == GL_TEXTURE_2D);
    bound_texture = static_cast<GLint>(texture);
}
void glTexParameteri(GLenum target, GLenum, GLint) { assert(target == GL_TEXTURE_2D); }
void glPixelStorei(GLenum pname, GLint value) {
    assert(pname == GL_UNPACK_ALIGNMENT);
    unpack_alignment = value;
}
void glGetIntegerv(GLenum pname, GLint *data) {
    assert(data != nullptr);
    if (pname == GL_TEXTURE_BINDING_2D) *data = bound_texture;
    else if (pname == GL_UNPACK_ALIGNMENT) *data = unpack_alignment;
    else *data = 0;
}
void glTexImage2D(GLenum target, GLint level, GLint internalformat, GLsizei width,
                  GLsizei height, GLint border, GLenum format, GLenum type, const void *pixels) {
    assert(target == GL_TEXTURE_2D && level == 0 && internalformat == static_cast<GLint>(GL_RGBA));
    assert(border == 0 && format == GL_RGBA && type == GL_UNSIGNED_BYTE && pixels != nullptr);
    ++tex_image_calls;
    uploaded_width = width;
    uploaded_height = height;
    last_upload_pixels = static_cast<const unsigned char *>(pixels);
    uploaded_size = static_cast<std::size_t>(width) * static_cast<std::size_t>(height) * 4u;
    if (fail_upload) pending_error = 0x0502u;
}
GLenum glGetError(void) {
    const GLenum value = pending_error;
    pending_error = GL_NO_ERROR;
    return value;
}
void glActiveTexture(GLenum value) { assert(value == GL_TEXTURE0); ++active_texture_calls; }
int __android_log_print(int, const char *, const char *, ...) { return 0; }

int main(void) {
    const std::uint8_t pixels[16] = {0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15};
    char error[128] = {};
    std::uint32_t texture = 0u;
    TimTextureCache cache{};
    bound_texture = 77;
    unpack_alignment = 8;
    assert(tim_texture_cache_init(&cache, 2u, 20u, error, sizeof(error)) == 0);
    const int first_upload_result = tim_texture_cache_upload_rgba(&cache, 10u, 2u, 2u, pixels, sizeof(pixels), &texture,
                                                                   error, sizeof(error));
    if (first_upload_result != 0) std::fprintf(stderr, "first upload failed: %s\n", error);
    assert(first_upload_result == 0);
    assert(texture != 0u && tex_image_calls == 1 && uploaded_width == 2 && uploaded_height == 2);
    assert(uploaded_size == sizeof(pixels));
    assert(std::memcmp(last_upload_pixels, pixels, sizeof(pixels)) == 0);
    assert(bound_texture == 77 && unpack_alignment == 8);
    const std::uint32_t first_texture = texture;
    assert(tim_texture_cache_upload_rgba(&cache, 10u, 2u, 2u, pixels, sizeof(pixels), &texture,
                                         error, sizeof(error)) == 0);
    assert(texture == first_texture && tex_image_calls == 1);
    assert(tim_texture_cache_lookup(&cache, 10u, &texture) == 0 && texture == first_texture);
    std::uint8_t other_pixels[16] = {};
    assert(tim_texture_cache_upload_rgba(&cache, 10u, 2u, 2u, other_pixels, sizeof(other_pixels), &texture,
                                         error, sizeof(error)) == -1);
    assert(tim_texture_cache_upload_rgba(&cache, 11u, 1u, 1u, pixels, 4u, &texture,
                                         error, sizeof(error)) == 0);
    assert(cache.used_bytes == 20u);
    assert(tim_texture_cache_upload_rgba(&cache, 12u, 1u, 1u, pixels, 4u, &texture,
                                         error, sizeof(error)) == -1);
    assert(tim_texture_cache_upload_rgba(&cache, 12u, 2u, 2u, pixels, 15u, &texture,
                                         error, sizeof(error)) == -1);

    /* Context loss discards invalid GL names without deleting them in a new context. */
    const int delete_count_before_loss = texture_delete_calls;
    tim_texture_cache_context_lost(&cache);
    assert(cache.count == 0u && cache.used_bytes == 0u);
    assert(texture_delete_calls == delete_count_before_loss);
    assert(tim_texture_cache_lookup(&cache, 10u, &texture) == -1);
    assert(tim_texture_cache_upload_rgba(&cache, 10u, 2u, 2u, pixels, sizeof(pixels), &texture,
                                         error, sizeof(error)) == 0);
    tim_texture_cache_destroy(&cache);
    assert(cache.entries == nullptr && cache.count == 0u);
    assert(texture_delete_calls == delete_count_before_loss + 1);

    /* GL upload and name allocation failure paths fail closed and retain no entries. */
    TimTextureCache failed_cache{};
    assert(tim_texture_cache_init(&failed_cache, 1u, 4u, error, sizeof(error)) == 0);
    fail_upload = true;
    assert(tim_texture_cache_upload_rgba(&failed_cache, 1u, 1u, 1u, pixels, 4u, &texture,
                                         error, sizeof(error)) == -1);
    assert(failed_cache.count == 0u && failed_cache.used_bytes == 0u);
    const int deletes_after_upload_failure = texture_delete_calls;
    assert(deletes_after_upload_failure > 0);
    fail_upload = false;
    fail_gen = true;
    assert(tim_texture_cache_upload_rgba(&failed_cache, 1u, 1u, 1u, pixels, 4u, &texture,
                                         error, sizeof(error)) == -1);
    assert(failed_cache.count == 0u);
    fail_gen = false;
    assert(tim_texture_cache_upload_rgba(&failed_cache, 1u, 1u, 1u, pixels, 4u, &texture,
                                         error, sizeof(error)) == 0);
    tim_texture_cache_destroy(&failed_cache);

    assert(tim_sprite_renderer_surface_created(error, sizeof(error)) == 0);
    const int programs_before_recreate = program_delete_calls;
    /* Surface recreation drops old-context names without deleting them. */
    assert(tim_sprite_renderer_surface_created(error, sizeof(error)) == 0);
    assert(program_delete_calls == programs_before_recreate);
    assert(tim_sprite_renderer_draw(7u, 100u, 50u, 320.0f, 240.0f,
                                    10.0f, 20.0f, 30.0f, 15.0f,
                                    10u, 5u, 20u, 10u, 1.0f, 1.0f, 1.0f, 1.0f) == 0);
    assert(draw_calls == 1 && active_texture_calls == 1);
    assert(position_enabled == false && uv_enabled == false);
    assert(std::fabs(captured_vertices[0][0] - 10.0f) < 0.001f);
    assert(std::fabs(captured_vertices[0][1] - 20.0f) < 0.001f);
    assert(std::fabs(captured_vertices[0][2] - 0.1f) < 0.001f);
    assert(std::fabs(captured_vertices[0][3] - 0.1f) < 0.001f);
    assert(std::fabs(captured_vertices[2][0] - 40.0f) < 0.001f);
    assert(std::fabs(captured_vertices[2][1] - 35.0f) < 0.001f);
    assert(std::fabs(captured_vertices[2][2] - 0.3f) < 0.001f);
    assert(std::fabs(captured_vertices[2][3] - 0.3f) < 0.001f);
    assert(tim_sprite_renderer_draw(7u, 100u, 50u, 320.0f, 240.0f,
                                    10.0f, 20.0f, 30.0f, 15.0f,
                                    95u, 0u, 20u, 10u, 1.0f, 1.0f, 1.0f, 1.0f) == -1);
    assert(tim_sprite_renderer_draw(7u, 100u, 50u, 320.0f, 240.0f,
                                    10.0f, 20.0f, 0.0f, 15.0f,
                                    10u, 5u, 20u, 10u, 1.0f, 1.0f, 1.0f, 1.0f) == -1);
    assert(draw_calls == 1);

    compile_ok = false;
    assert(tim_sprite_renderer_surface_created(error, sizeof(error)) == -1);
    assert(tim_sprite_renderer_draw(7u, 100u, 50u, 320.0f, 240.0f,
                                    0.0f, 0.0f, 10.0f, 10.0f,
                                    0u, 0u, 10u, 10u, 1.0f, 1.0f, 1.0f, 1.0f) == -1);
    compile_ok = true;
    locations_ok = false;
    assert(tim_sprite_renderer_surface_created(error, sizeof(error)) == -1);
    locations_ok = true;
    return 0;
}
'''


def test_tim_texture_cache_and_sprite_quad_mock(tmp_path: pathlib.Path) -> None:
    compiler = shutil.which("clang++") or shutil.which("g++")
    assert compiler is not None, "a C++17 compiler is required for GLES mock testing"
    harness = tmp_path / "tim_texture_harness.cpp"
    executable = tmp_path / "tim_texture_harness"
    harness.write_text(HARNESS, encoding="utf-8")
    result = subprocess.run(
        [compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-Wconversion",
         "-Wsign-conversion", "-pedantic", "-I", str(STUB_DIR), "-I", str(GAME_DIR),
         str(harness), str(GAME_DIR / "tim_texture_renderer.cpp"), "-o", str(executable)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    run = subprocess.run([str(executable)], capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
