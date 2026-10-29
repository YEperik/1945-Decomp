"""Compile-and-run tests for the explicitly labelled native gameplay prototype."""
from __future__ import annotations

import os
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
GAME_DIR = ROOT / "app/src/main/cpp/game"

HARNESS = r'''#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <string.h>
#include "game_core.h"

static unsigned count_bullets(const GameWorld *w) {
    unsigned count = 0;
    for (unsigned i = 0; i < GAME_MAX_PLAYER_BULLETS; ++i) count += w->player_bullets[i].active != 0u;
    return count;
}
static unsigned count_enemies(const GameWorld *w) {
    unsigned count = 0;
    for (unsigned i = 0; i < GAME_MAX_ENEMIES; ++i) count += w->enemies[i].active != 0u;
    return count;
}

int main(void) {
    GameWorld a, b;
    GameInput input = {0.0f, 0.0f, 0u, 0u};
    game_world_init(&a, 0x1945u);
    game_world_init(&b, 0x1945u);
    assert(a.state == GAME_STATE_READY && a.lives == 3);
    assert(a.player_x == 160.0f && a.player_y == 208.0f);
    assert(game_world_update(&a, NAN, input) == GAME_AUDIO_NONE);
    assert(game_world_update(&a, INFINITY, input) == GAME_AUDIO_NONE);
    assert(game_world_update(NULL, 1.0f / 60.0f, input) == GAME_AUDIO_NONE);

    input.move_x = NAN; input.move_y = INFINITY; input.fire_down = 1u;
    uint32_t events = game_world_update(&a, 1.0f / 60.0f, input);
    (void)game_world_update(&b, 1.0f / 60.0f, input);
    assert(a.state == GAME_STATE_PLAYING);
    assert((events & GAME_AUDIO_START) != 0u);
    assert((events & GAME_AUDIO_FIRE) != 0u);
    assert(count_bullets(&a) == 1u);
    assert(count_bullets(&b) == 1u);
    assert(isfinite(a.player_x) && isfinite(a.player_y));

    /* Deterministic simulation with identical seed and input sequence. */
    input.move_x = 0.25f; input.move_y = -0.5f; input.fire_down = 1u;
    for (unsigned i = 0; i < 900u; ++i) {
        float dt = (i % 4u == 0u) ? 1.0f / 30.0f : 1.0f / 60.0f;
        (void)game_world_update(&a, dt, input);
        (void)game_world_update(&b, dt, input);
    }
    assert(a.score == b.score);
    assert(a.lives == b.lives);
    assert(a.tick_count == b.tick_count);
    assert(a.player_x == b.player_x && a.player_y == b.player_y);
    assert(count_enemies(&a) <= GAME_MAX_ENEMIES);

    /* A pause press is latched until the next simulation tick, including at 120 Hz. */
    game_world_init(&a, 42u);
    input.move_x = 0.0f; input.move_y = 0.0f; input.fire_down = 1u; input.pause_pressed = 0u;
    (void)game_world_update(&a, 1.0f / 60.0f, input);
    assert(a.state == GAME_STATE_PLAYING);
    input.fire_down = 0u; input.pause_pressed = 1u;
    (void)game_world_update(&a, 0.002f, input);
    assert(a.state == GAME_STATE_PLAYING);
    input.pause_pressed = 0u;
    (void)game_world_update(&a, 0.02f, input);
    assert(a.state == GAME_STATE_PAUSED);
    input.fire_down = 1u;
    (void)game_world_update(&a, 1.0f / 60.0f, input);
    assert(a.state == GAME_STATE_PAUSED); /* Fire must not accidentally resume. */
    input.fire_down = 0u; input.pause_pressed = 1u;
    (void)game_world_update(&a, 1.0f / 60.0f, input);
    assert(a.state == GAME_STATE_PLAYING);

    /* Lifecycle pause must discard a pause edge that has not reached a fixed tick. */
    input.pause_pressed = 1u;
    (void)game_world_update(&a, 0.002f, input);
    assert(a.pause_latched == 1u && a.state == GAME_STATE_PLAYING);
    game_world_force_pause(&a);
    assert(a.state == GAME_STATE_PAUSED);
    assert(a.pause_latched == 0u && a.accumulator == 0.0f);
    input.pause_pressed = 0u;
    (void)game_world_update(&a, 1.0f / 60.0f, input);
    assert(a.state == GAME_STATE_PAUSED); /* Lifecycle pause must not auto-resume. */

    /* Movement is normalized/clamped and remains inside the logical playfield. */
    input.pause_pressed = 0u; input.move_x = 100.0f; input.move_y = -100.0f;
    for (unsigned i = 0; i < 500u; ++i) (void)game_world_update(&a, 1.0f / 60.0f, input);
    assert(a.player_x >= 9.0f && a.player_x <= 311.0f);
    assert(a.player_y >= 35.0f && a.player_y <= 229.0f);

    /* A direct collision fixture verifies damage, game over, and fire-to-restart. */
    game_world_init(&a, 7u);
    input.move_x = 0.0f; input.move_y = 0.0f; input.fire_down = 1u;
    (void)game_world_update(&a, 1.0f / 60.0f, input);
    a.lives = 1;
    a.invulnerability_timer = 0.0f;
    a.enemy_shots[0].x = a.player_x;
    a.enemy_shots[0].y = a.player_y;
    a.enemy_shots[0].vx = 0.0f;
    a.enemy_shots[0].vy = 0.0f;
    a.enemy_shots[0].active = 1u;
    input.fire_down = 0u;
    events = game_world_update(&a, 1.0f / 60.0f, input);
    assert(a.lives == 0 && a.state == GAME_STATE_GAME_OVER);
    assert((events & GAME_AUDIO_PLAYER_HIT) != 0u);
    assert((events & GAME_AUDIO_GAME_OVER) != 0u);
    input.fire_down = 1u;
    events = game_world_update(&a, 1.0f / 60.0f, input);
    assert(a.state == GAME_STATE_PLAYING && a.lives == 3);
    assert((events & GAME_AUDIO_START) != 0u);

    game_world_reset(&a, 0u);
    assert(a.state == GAME_STATE_READY && a.lives == 3 && a.score == 0u);
    return 0;
}
'''


def _compile_and_run(tmp_path: pathlib.Path, compiler: str, sanitizers: bool = False) -> None:
    harness = tmp_path / "game_core_harness.c"
    exe = tmp_path / f"game_core_{pathlib.Path(compiler).name}"
    harness.write_text(HARNESS, encoding="utf-8")
    command = [
        compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wconversion",
        "-Wsign-conversion", "-pedantic", "-I", str(GAME_DIR),
        str(harness), str(GAME_DIR / "game_core.c"), "-lm", "-o", str(exe),
    ]
    if sanitizers:
        command[1:1] = ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
    subprocess.run(command, check=True, capture_output=True, text=True)
    env = os.environ.copy()
    if sanitizers:
        env.setdefault("ASAN_OPTIONS", "detect_leaks=0:halt_on_error=1")
        env.setdefault("UBSAN_OPTIONS", "halt_on_error=1:print_stacktrace=1")
    subprocess.run([str(exe)], check=True, capture_output=True, text=True, env=env)


def test_native_game_core_behavior(tmp_path: pathlib.Path) -> None:
    _compile_and_run(tmp_path, "gcc")


def test_native_game_core_asan_ubsan(tmp_path: pathlib.Path) -> None:
    _compile_and_run(tmp_path, "clang", sanitizers=True)
