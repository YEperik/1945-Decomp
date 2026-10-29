"""Run the GLES2 renderer against a deterministic mock to verify bounds and failure paths."""
from __future__ import annotations

import pathlib
import shutil
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
GAME_DIR = ROOT / "app/src/main/cpp/game"
STUB_DIR = ROOT / "tests/native_stubs"

HARNESS = r'''#include <cassert>
#include <cstdarg>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include "GLES2/gl2.h"
#include "game_renderer.h"
#include "android/log.h"

static bool compile_ok = true;
static bool link_ok = true;
static bool locations_ok = true;
static bool buffer_ok = true;
static GLuint next_name = 1u;
static std::size_t allocated_bytes = 0u;
static std::size_t uploaded_bytes = 0u;
static GLsizei draw_count = 0;
static int draw_calls = 0;
static int program_deletes = 0;
static int log_calls = 0;
static GLint viewport_x = 0;
static GLint viewport_y = 0;
static GLsizei viewport_w = 0;
static GLsizei viewport_h = 0;

GLuint glCreateShader(GLenum) { return next_name++; }
void glShaderSource(GLuint, GLsizei, const GLchar *const *, const GLint *) {}
void glCompileShader(GLuint) {}
void glGetShaderiv(GLuint, GLenum pname, GLint *params) {
    if (pname == GL_COMPILE_STATUS) *params = compile_ok ? GL_TRUE : GL_FALSE;
    else if (pname == GL_INFO_LOG_LENGTH) *params = compile_ok ? 0 : 16;
    else *params = 0;
}
void glGetShaderInfoLog(GLuint, GLsizei, GLsizei *length, GLchar *buffer) {
    if (length) *length = 0;
    if (buffer) buffer[0] = '\0';
}
void glDeleteShader(GLuint) {}
void glDeleteBuffers(GLsizei, const GLuint *) {}
void glDeleteProgram(GLuint) { ++program_deletes; }
GLuint glCreateProgram(void) { return next_name++; }
void glAttachShader(GLuint, GLuint) {}
void glBindAttribLocation(GLuint, GLuint, const GLchar *) {}
void glLinkProgram(GLuint) {}
void glGetProgramiv(GLuint, GLenum pname, GLint *params) {
    if (pname == GL_LINK_STATUS) *params = link_ok ? GL_TRUE : GL_FALSE;
    else if (pname == GL_INFO_LOG_LENGTH) *params = link_ok ? 0 : 16;
    else *params = 0;
}
void glGetProgramInfoLog(GLuint, GLsizei, GLsizei *length, GLchar *buffer) {
    if (length) *length = 0;
    if (buffer) buffer[0] = '\0';
}
GLint glGetAttribLocation(GLuint, const GLchar *name) {
    if (!locations_ok) return -1;
    if (std::strcmp(name, "a_position") == 0) return 0;
    if (std::strcmp(name, "a_color") == 0) return 1;
    return -1;
}
GLint glGetUniformLocation(GLuint, const GLchar *) { return locations_ok ? 2 : -1; }
void glGenBuffers(GLsizei n, GLuint *buffers) {
    for (GLsizei i = 0; i < n; ++i) buffers[i] = buffer_ok ? next_name++ : 0u;
}
void glBindBuffer(GLenum, GLuint) {}
void glBufferData(GLenum, GLsizeiptr size, const void *, GLenum) {
    assert(size >= 0);
    allocated_bytes = static_cast<std::size_t>(size);
}
void glDisable(GLenum) {}
void glEnable(GLenum) {}
void glBlendFunc(GLenum, GLenum) {}
void glViewport(GLint x, GLint y, GLsizei width, GLsizei height) {
    viewport_x = x; viewport_y = y; viewport_w = width; viewport_h = height;
}
void glClearColor(GLfloat, GLfloat, GLfloat, GLfloat) {}
void glClear(GLenum) {}
void glUseProgram(GLuint) {}
void glUniform2f(GLint, GLfloat, GLfloat) {}
void glBufferSubData(GLenum, GLintptr offset, GLsizeiptr size, const void *data) {
    assert(offset == 0);
    assert(size >= 0);
    assert(static_cast<std::size_t>(size) <= allocated_bytes);
    assert(data != nullptr || size == 0);
    uploaded_bytes = static_cast<std::size_t>(size);
}
void glEnableVertexAttribArray(GLuint) {}
void glVertexAttribPointer(GLuint, GLint, GLenum, GLboolean, GLsizei, const void *) {}
void glDrawArrays(GLenum mode, GLint first, GLsizei count) {
    assert(mode == GL_TRIANGLES);
    assert(first == 0);
    assert(count > 0 && count <= 16384);
    assert((count % 3) == 0);
    draw_count = count;
    ++draw_calls;
}
void glDisableVertexAttribArray(GLuint) {}
int __android_log_print(int, const char *, const char *, ...) { ++log_calls; return 0; }

int main(void) {
    GameWorld world{};
    world.state = GAME_STATE_READY;
    world.player_x = 160.0f;
    world.player_y = 208.0f;
    world.lives = 3;

    /* Shader failure must fail closed without submitting a draw. */
    compile_ok = false;
    game_renderer_surface_created();
    game_renderer_surface_changed(480, 320);
    game_renderer_draw(&world);
    assert(draw_calls == 0);
    assert(log_calls > 0);

    /* Missing shader locations and a failed VBO allocation must both fail closed. */
    compile_ok = true;
    locations_ok = false;
    int deletes_before_location_failure = program_deletes;
    game_renderer_surface_created();
    game_renderer_draw(&world);
    assert(draw_calls == 0);
    assert(program_deletes == deletes_before_location_failure + 1);
    locations_ok = true;
    buffer_ok = false;
    int deletes_before_buffer_failure = program_deletes;
    game_renderer_surface_created();
    game_renderer_draw(&world);
    assert(draw_calls == 0);
    assert(program_deletes == deletes_before_buffer_failure + 1);
    buffer_ok = true;

    /* Healthy setup submits bounded geometry into the allocated VBO. */
    game_renderer_surface_created();
    game_renderer_surface_changed(480, 320);
    game_renderer_draw(&world);
    assert(draw_calls == 1);
    assert(draw_count > 0 && draw_count <= 16384 && (draw_count % 3) == 0);
    assert(allocated_bytes >= uploaded_bytes && uploaded_bytes > 0u);
    assert(viewport_w == 426 && viewport_h == 320);
    assert(viewport_x == 27 && viewport_y == 0);

    /* A recreated EGL context must reset names without deleting old-context names. */
    int deletes_before_recreate = program_deletes;
    game_renderer_surface_created();
    assert(program_deletes == deletes_before_recreate);
    game_renderer_surface_changed(1080, 2400);
    game_renderer_draw(&world);
    assert(viewport_w == 1080 && viewport_h == 810);
    assert(viewport_x == 0 && viewport_y == 795);
    assert(allocated_bytes >= uploaded_bytes && uploaded_bytes > 0u);
    assert(draw_calls == 2);
    return 0;
}
'''


def test_gles2_renderer_mock_failure_path_viewport_and_buffer_bounds(tmp_path: pathlib.Path) -> None:
    compiler = shutil.which("clang++") or shutil.which("g++")
    assert compiler is not None, "a C++17 compiler is required for renderer mock testing"
    harness = tmp_path / "renderer_mock_harness.cpp"
    executable = tmp_path / "renderer_mock_harness"
    harness.write_text(HARNESS, encoding="utf-8")
    result = subprocess.run(
        [compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-Wconversion",
         "-Wsign-conversion", "-pedantic", "-I", str(STUB_DIR), "-I", str(GAME_DIR),
         str(harness), str(GAME_DIR / "game_renderer.cpp"), "-o", str(executable)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    run = subprocess.run([str(executable)], capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
