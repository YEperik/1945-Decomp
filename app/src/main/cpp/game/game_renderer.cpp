#include "game_renderer.h"

#include <GLES2/gl2.h>
#include <android/log.h>

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>

namespace {
constexpr const char *kLogTag = "1945Renderer";
constexpr std::size_t kMaxVertices = 16384;
constexpr float kLogicalWidth = 320.0f;
constexpr float kLogicalHeight = 240.0f;

struct Vertex {
    GLfloat x;
    GLfloat y;
    GLfloat r;
    GLfloat g;
    GLfloat b;
    GLfloat a;
};

struct Color {
    GLfloat r;
    GLfloat g;
    GLfloat b;
    GLfloat a;
};

Vertex g_vertices[kMaxVertices];
std::size_t g_vertex_count = 0;
GLuint g_program = 0;
GLuint g_vertex_buffer = 0;
GLint g_position_location = -1;
GLint g_color_location = -1;
GLint g_resolution_location = -1;
GLint g_viewport_x = 0;
GLint g_viewport_y = 0;
GLint g_viewport_width = 1;
GLint g_viewport_height = 1;
float g_scene_time = 0.0f;

constexpr Color kWhite{0.90f, 0.95f, 1.0f, 1.0f};
constexpr Color kCyan{0.2f, 0.8f, 1.0f, 1.0f};
constexpr Color kRed{1.0f, 0.24f, 0.18f, 1.0f};
constexpr Color kGold{1.0f, 0.76f, 0.15f, 1.0f};
constexpr Color kDarkBlue{0.025f, 0.045f, 0.12f, 1.0f};

constexpr std::uint8_t kFont[36][7] = {
    {14,17,19,21,25,17,14}, {4,12,4,4,4,4,14}, {14,17,1,2,4,8,31},
    {30,1,1,14,1,1,30}, {2,6,10,18,31,2,2}, {31,16,16,30,1,1,30},
    {6,8,16,30,17,17,14}, {31,1,2,4,8,8,8}, {14,17,17,14,17,17,14},
    {14,17,17,15,1,2,12},
    {14,17,17,31,17,17,17}, {30,17,17,30,17,17,30},
    {14,17,16,16,16,17,14}, {28,18,17,17,17,18,28},
    {31,16,16,30,16,16,31}, {31,16,16,30,16,16,16},
    {14,17,16,23,17,17,15}, {17,17,17,31,17,17,17},
    {14,4,4,4,4,4,14}, {7,2,2,2,2,18,12},
    {17,18,20,24,20,18,17}, {16,16,16,16,16,16,31},
    {17,27,21,21,17,17,17}, {17,25,21,19,17,17,17},
    {14,17,17,17,17,17,14}, {30,17,17,30,16,16,16},
    {14,17,17,17,21,18,13}, {30,17,17,30,20,18,17},
    {15,16,16,14,1,1,30}, {31,4,4,4,4,4,4},
    {17,17,17,17,17,17,14}, {17,17,17,17,17,10,4},
    {17,17,17,21,21,21,10}, {17,17,10,4,10,17,17},
    {17,17,10,4,4,4,4}, {31,1,2,4,8,16,31}
};

GLuint compile_shader(GLenum type, const char *source)
{
    GLuint shader = glCreateShader(type);
    GLint compiled = GL_FALSE;
    if (shader == 0u) {
        return 0u;
    }
    glShaderSource(shader, 1, &source, nullptr);
    glCompileShader(shader);
    glGetShaderiv(shader, GL_COMPILE_STATUS, &compiled);
    if (compiled != GL_TRUE) {
        GLint log_length = 0;
        glGetShaderiv(shader, GL_INFO_LOG_LENGTH, &log_length);
        if (log_length > 1) {
            char log_buffer[512] = {};
            GLsizei written = 0;
            glGetShaderInfoLog(shader, static_cast<GLsizei>(sizeof(log_buffer)), &written, log_buffer);
            __android_log_print(ANDROID_LOG_ERROR, kLogTag, "Shader compile failed: %s", log_buffer);
        }
        glDeleteShader(shader);
        return 0u;
    }
    return shader;
}

void add_vertex(float x, float y, Color color)
{
    if (g_vertex_count >= kMaxVertices) {
        return;
    }
    Vertex &vertex = g_vertices[g_vertex_count++];
    vertex.x = x;
    vertex.y = y;
    vertex.r = color.r;
    vertex.g = color.g;
    vertex.b = color.b;
    vertex.a = color.a;
}

void triangle(float ax, float ay, float bx, float by, float cx, float cy, Color color)
{
    if (g_vertex_count + 3u > kMaxVertices) {
        return;
    }
    add_vertex(ax, ay, color);
    add_vertex(bx, by, color);
    add_vertex(cx, cy, color);
}

void quad(float x, float y, float width, float height, Color color)
{
    triangle(x, y, x + width, y, x + width, y + height, color);
    triangle(x, y, x + width, y + height, x, y + height, color);
}

void circle(float cx, float cy, float radius, Color color, int segments)
{
    const float pi = 3.14159265358979323846f;
    for (int i = 0; i < segments; ++i) {
        const float a0 = (static_cast<float>(i) / static_cast<float>(segments)) * 2.0f * pi;
        const float a1 = (static_cast<float>(i + 1) / static_cast<float>(segments)) * 2.0f * pi;
        triangle(cx, cy,
                 cx + std::cos(a0) * radius, cy + std::sin(a0) * radius,
                 cx + std::cos(a1) * radius, cy + std::sin(a1) * radius,
                 color);
    }
}

int glyph_index(char c)
{
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'A' && c <= 'Z') return 10 + c - 'A';
    return -1;
}

void draw_text(const char *text, float x, float y, float scale, Color color)
{
    if (text == nullptr) return;
    for (const char *cursor = text; *cursor != '\0'; ++cursor) {
        const char c = (*cursor >= 'a' && *cursor <= 'z')
            ? static_cast<char>(*cursor - 'a' + 'A') : *cursor;
        const int index = glyph_index(c);
        if (index >= 0) {
            for (int row = 0; row < 7; ++row) {
                const std::uint8_t bits = kFont[index][row];
                for (int col = 0; col < 5; ++col) {
                    if ((bits & static_cast<std::uint8_t>(1u << (4 - col))) != 0u) {
                        quad(x + static_cast<float>(col) * scale,
                             y + static_cast<float>(row) * scale,
                             scale, scale, color);
                    }
                }
            }
        } else if (c == ':') {
            quad(x + 2.0f * scale, y + 2.0f * scale, scale, scale, color);
            quad(x + 2.0f * scale, y + 5.0f * scale, scale, scale, color);
        } else if (c == '-') {
            quad(x + scale, y + 3.0f * scale, 3.0f * scale, scale, color);
        } else if (c == '.') {
            quad(x + 2.0f * scale, y + 6.0f * scale, scale, scale, color);
        } else if (c == '/') {
            for (int k = 0; k < 5; ++k) {
                quad(x + static_cast<float>(4 - k) * scale,
                     y + static_cast<float>(k) * scale, scale, scale, color);
            }
        }
        x += 6.0f * scale;
    }
}

void draw_ship(float x, float y, bool player)
{
    if (player) {
        triangle(x, y - 8.0f, x - 6.0f, y + 6.0f, x + 6.0f, y + 6.0f, kCyan);
        triangle(x, y - 2.0f, x - 2.0f, y + 4.0f, x + 2.0f, y + 4.0f, kWhite);
        triangle(x - 4.0f, y + 3.0f, x - 8.0f, y + 7.0f, x - 2.0f, y + 6.0f,
                 Color{0.15f, 0.45f, 1.0f, 1.0f});
        triangle(x + 4.0f, y + 3.0f, x + 8.0f, y + 7.0f, x + 2.0f, y + 6.0f,
                 Color{0.15f, 0.45f, 1.0f, 1.0f});
    } else {
        triangle(x, y + 7.0f, x - 6.0f, y - 5.0f, x + 6.0f, y - 5.0f, kRed);
        quad(x - 2.0f, y - 2.0f, 4.0f, 4.0f, kGold);
    }
}

void append_game_scene(const GameWorld *world)
{
    char text[48];
    g_vertex_count = 0u;
    g_scene_time = world->elapsed;
    quad(0.0f, 0.0f, kLogicalWidth, kLogicalHeight, kDarkBlue);
    for (int i = 0; i < 62; ++i) {
        const float base_x = static_cast<float>((i * 47 + 13) % 319);
        const float base_y = static_cast<float>((i * 71 + 19) % 240);
        const float speed = 8.0f + static_cast<float>(i % 9) * 2.0f;
        float star_y = std::fmod(base_y + g_scene_time * speed, kLogicalHeight);
        if (star_y < 0.0f) star_y += kLogicalHeight;
        const float size = (i % 7 == 0) ? 2.0f : 1.0f;
        Color star_color = (i % 4 == 0) ? kCyan : Color{0.38f, 0.49f, 0.70f, 0.82f};
        quad(base_x, star_y, size, size, star_color);
    }

    for (std::size_t i = 0u; i < GAME_MAX_PLAYER_BULLETS; ++i) {
        const GameBullet &bullet = world->player_bullets[i];
        if (bullet.active != 0u) {
            quad(bullet.x - 1.0f, bullet.y - 3.0f, 2.0f, 6.0f, kGold);
        }
    }
    for (std::size_t i = 0u; i < GAME_MAX_ENEMY_SHOTS; ++i) {
        const GameEnemyShot &shot = world->enemy_shots[i];
        if (shot.active != 0u) {
            circle(shot.x, shot.y, 2.4f, kRed, 8);
        }
    }
    for (std::size_t i = 0u; i < GAME_MAX_ENEMIES; ++i) {
        const GameEnemy &enemy = world->enemies[i];
        if (enemy.active != 0u) {
            draw_ship(enemy.x, enemy.y, false);
        }
    }

    if (world->invulnerability_timer <= 0.0f ||
        (static_cast<int>(world->invulnerability_timer * 12.0f) % 2) == 0) {
        draw_ship(world->player_x, world->player_y, true);
    }

    draw_text("1945 NATIVE PROTOTYPE", 7.0f, 7.0f, 1.0f, kWhite);
    (void)std::snprintf(text, sizeof(text), "SCORE %06u", static_cast<unsigned>(world->score % 1000000u));
    draw_text(text, 7.0f, 19.0f, 1.0f, kGold);
    (void)std::snprintf(text, sizeof(text), "LIVES %d", static_cast<int>(world->lives));
    draw_text(text, 7.0f, 31.0f, 1.0f, kCyan);

    circle(58.0f, 193.0f, 31.0f, Color{0.15f, 0.40f, 0.85f, 0.18f}, 20);
    circle(58.0f, 193.0f, 31.0f, Color{0.35f, 0.65f, 1.0f, 0.65f}, 20);
    circle(58.0f, 193.0f, 9.0f, Color{0.3f, 0.7f, 1.0f, 0.6f}, 16);
    circle(269.0f, 193.0f, 22.0f, Color{1.0f, 0.20f, 0.10f, 0.15f}, 20);
    circle(269.0f, 193.0f, 22.0f, Color{1.0f, 0.35f, 0.25f, 0.72f}, 20);
    draw_text("FIRE", 257.0f, 191.0f, 1.0f, kWhite);
    quad(278.0f, 7.0f, 35.0f, 13.0f, Color{0.15f, 0.24f, 0.42f, 0.92f});
    draw_text("PAUSE", 280.0f, 10.0f, 1.0f, kWhite);

    if (world->state == GAME_STATE_READY) {
        quad(36.0f, 91.0f, 248.0f, 48.0f, Color{0.01f, 0.025f, 0.08f, 0.80f});
        draw_text("READY", 127.0f, 99.0f, 2.0f, kGold);
        draw_text("FIRE TO START", 106.0f, 119.0f, 1.0f, kWhite);
    } else if (world->state == GAME_STATE_PAUSED) {
        quad(36.0f, 91.0f, 248.0f, 48.0f, Color{0.01f, 0.025f, 0.08f, 0.82f});
        draw_text("PAUSED", 124.0f, 99.0f, 2.0f, kGold);
        draw_text("TAP PAUSE TO RESUME", 85.0f, 119.0f, 1.0f, kWhite);
    } else if (world->state == GAME_STATE_GAME_OVER) {
        quad(35.0f, 88.0f, 250.0f, 56.0f, Color{0.04f, 0.005f, 0.02f, 0.88f});
        draw_text("GAME OVER", 110.0f, 96.0f, 2.0f, kRed);
        draw_text("FIRE TO RESTART", 101.0f, 120.0f, 1.0f, kWhite);
    }
}
} // namespace

extern "C" void game_renderer_surface_created(void)
{
    static const char *vertex_source =
        "attribute vec2 a_position;\n"
        "attribute vec4 a_color;\n"
        "uniform vec2 u_resolution;\n"
        "varying vec4 v_color;\n"
        "void main() {\n"
        "  vec2 clip = (a_position / u_resolution) * 2.0 - 1.0;\n"
        "  gl_Position = vec4(clip.x, -clip.y, 0.0, 1.0);\n"
        "  v_color = a_color;\n"
        "}\n";
    static const char *fragment_source =
        "precision mediump float;\n"
        "varying vec4 v_color;\n"
        "void main() { gl_FragColor = v_color; }\n";

    /* onSurfaceCreated means a new EGL context may have replaced the old one.
       Old GL names are invalid in the new context, so reset names without
       deleting IDs that might be reused by unrelated objects in this context. */
    g_vertex_buffer = 0u;
    g_program = 0u;
    g_position_location = -1;
    g_color_location = -1;
    g_resolution_location = -1;

    const GLuint vertex_shader = compile_shader(GL_VERTEX_SHADER, vertex_source);
    const GLuint fragment_shader = compile_shader(GL_FRAGMENT_SHADER, fragment_source);
    if (vertex_shader == 0u || fragment_shader == 0u) {
        if (vertex_shader != 0u) glDeleteShader(vertex_shader);
        if (fragment_shader != 0u) glDeleteShader(fragment_shader);
        return;
    }
    g_program = glCreateProgram();
    if (g_program == 0u) {
        glDeleteShader(vertex_shader);
        glDeleteShader(fragment_shader);
        return;
    }
    glAttachShader(g_program, vertex_shader);
    glAttachShader(g_program, fragment_shader);
    glBindAttribLocation(g_program, 0u, "a_position");
    glBindAttribLocation(g_program, 1u, "a_color");
    glLinkProgram(g_program);
    glDeleteShader(vertex_shader);
    glDeleteShader(fragment_shader);
    GLint linked = GL_FALSE;
    glGetProgramiv(g_program, GL_LINK_STATUS, &linked);
    if (linked != GL_TRUE) {
        GLint log_length = 0;
        glGetProgramiv(g_program, GL_INFO_LOG_LENGTH, &log_length);
        if (log_length > 1) {
            char log_buffer[512] = {};
            GLsizei written = 0;
            glGetProgramInfoLog(g_program, static_cast<GLsizei>(sizeof(log_buffer)), &written, log_buffer);
            __android_log_print(ANDROID_LOG_ERROR, kLogTag, "Program link failed: %s", log_buffer);
        }
        glDeleteProgram(g_program);
        g_program = 0u;
        return;
    }
    g_position_location = glGetAttribLocation(g_program, "a_position");
    g_color_location = glGetAttribLocation(g_program, "a_color");
    g_resolution_location = glGetUniformLocation(g_program, "u_resolution");
    if (g_position_location < 0 || g_color_location < 0 || g_resolution_location < 0) {
        __android_log_print(ANDROID_LOG_ERROR, kLogTag,
                            "Required shader attribute/uniform was not found");
        glDeleteProgram(g_program);
        g_program = 0u;
        return;
    }
    glGenBuffers(1, &g_vertex_buffer);
    if (g_vertex_buffer == 0u) {
        __android_log_print(ANDROID_LOG_ERROR, kLogTag, "Unable to create renderer vertex buffer");
        glDeleteProgram(g_program);
        g_program = 0u;
        return;
    }
    glBindBuffer(GL_ARRAY_BUFFER, g_vertex_buffer);
    glBufferData(GL_ARRAY_BUFFER, static_cast<GLsizeiptr>(sizeof(g_vertices)), nullptr, GL_STREAM_DRAW);
    glBindBuffer(GL_ARRAY_BUFFER, 0u);
    glDisable(GL_DEPTH_TEST);
    glEnable(GL_BLEND);
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
}

extern "C" void game_renderer_surface_changed(int width, int height)
{
    if (width <= 0) width = 1;
    if (height <= 0) height = 1;
    const float scale = std::min(static_cast<float>(width) / kLogicalWidth,
                                 static_cast<float>(height) / kLogicalHeight);
    g_viewport_width = std::max(1, static_cast<int>(kLogicalWidth * scale));
    g_viewport_height = std::max(1, static_cast<int>(kLogicalHeight * scale));
    g_viewport_x = (width - g_viewport_width) / 2;
    g_viewport_y = (height - g_viewport_height) / 2;
    glViewport(0, 0, width, height);
}

extern "C" void game_renderer_draw(const GameWorld *world)
{
    if (world == nullptr) return;
    glClearColor(0.0f, 0.0f, 0.0f, 1.0f);
    glClear(GL_COLOR_BUFFER_BIT);
    glViewport(g_viewport_x, g_viewport_y, g_viewport_width, g_viewport_height);
    if (g_program == 0u || g_vertex_buffer == 0u) {
        return;
    }
    append_game_scene(world);
    glUseProgram(g_program);
    glUniform2f(g_resolution_location, kLogicalWidth, kLogicalHeight);
    glBindBuffer(GL_ARRAY_BUFFER, g_vertex_buffer);
    glBufferSubData(GL_ARRAY_BUFFER, 0,
                    static_cast<GLsizeiptr>(g_vertex_count * sizeof(Vertex)), g_vertices);
    glEnableVertexAttribArray(static_cast<GLuint>(g_position_location));
    glEnableVertexAttribArray(static_cast<GLuint>(g_color_location));
    glVertexAttribPointer(static_cast<GLuint>(g_position_location), 2, GL_FLOAT, GL_FALSE,
                          static_cast<GLsizei>(sizeof(Vertex)), reinterpret_cast<const void *>(offsetof(Vertex, x)));
    glVertexAttribPointer(static_cast<GLuint>(g_color_location), 4, GL_FLOAT, GL_FALSE,
                          static_cast<GLsizei>(sizeof(Vertex)), reinterpret_cast<const void *>(offsetof(Vertex, r)));
    glDrawArrays(GL_TRIANGLES, 0, static_cast<GLsizei>(g_vertex_count));
    glDisableVertexAttribArray(static_cast<GLuint>(g_position_location));
    glDisableVertexAttribArray(static_cast<GLuint>(g_color_location));
    glBindBuffer(GL_ARRAY_BUFFER, 0u);
}
