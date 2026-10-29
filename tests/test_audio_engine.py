"""Compile-and-run checks for bounded procedural PCM sound effects."""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
GAME_DIR = ROOT / "app/src/main/cpp/game"

HARNESS = r'''#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include "audio_engine.h"
#include "game_core.h"

int main(void) {
    AudioEngine engine;
    int16_t pcm[2048];
    audio_engine_init(&engine);
    audio_engine_render(&engine, GAME_AUDIO_NONE, pcm, 2048u);
    for (size_t i = 0; i < 2048u; ++i) assert(pcm[i] == 0);

    audio_engine_render(&engine, GAME_AUDIO_FIRE, pcm, 512u);
    int nonzero = 0;
    int16_t maximum = 0;
    int16_t minimum = 0;
    for (size_t i = 0; i < 512u; ++i) {
        if (pcm[i] != 0) ++nonzero;
        if (pcm[i] > maximum) maximum = pcm[i];
        if (pcm[i] < minimum) minimum = pcm[i];
    }
    assert(nonzero > 20);
    assert(maximum <= 6000 && minimum >= -6000);

    audio_engine_render(&engine, GAME_AUDIO_START | GAME_AUDIO_PLAYER_HIT |
                        GAME_AUDIO_GAME_OVER | GAME_AUDIO_PAUSE, pcm, 2048u);
    for (size_t i = 0; i < 2048u; ++i) assert(pcm[i] <= 25000 && pcm[i] >= -25000);
    audio_engine_render(NULL, GAME_AUDIO_FIRE, pcm, 2048u);
    for (size_t i = 0; i < 2048u; ++i) assert(pcm[i] == 0);
    audio_engine_render(&engine, GAME_AUDIO_FIRE, NULL, 512u);

    /* Reject impossible lengths before multiplying or touching a caller buffer. */
    int16_t sentinels[2] = {123, -456};
    audio_engine_render(NULL, GAME_AUDIO_FIRE, sentinels, SIZE_MAX);
    assert(sentinels[0] == 123 && sentinels[1] == -456);
    audio_engine_render(&engine, GAME_AUDIO_FIRE, sentinels, SIZE_MAX);
    assert(sentinels[0] == 123 && sentinels[1] == -456);
    return 0;
}
'''


def test_procedural_pcm_engine_is_bounded_and_active(tmp_path: pathlib.Path) -> None:
    harness = tmp_path / "audio_engine_harness.c"
    exe = tmp_path / "audio_engine_harness"
    harness.write_text(HARNESS, encoding="utf-8")
    subprocess.run(
        ["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wconversion",
         "-Wsign-conversion", "-pedantic", "-I", str(GAME_DIR), str(harness),
         str(GAME_DIR / "audio_engine.c"), "-lm", "-o", str(exe)],
        check=True, capture_output=True, text=True,
    )
    subprocess.run([str(exe)], check=True, capture_output=True, text=True)


def test_procedural_pcm_engine_asan_ubsan(tmp_path: pathlib.Path) -> None:
    compiler = shutil.which("clang")
    if compiler is None:
        import pytest
        pytest.skip("Clang is unavailable; sanitizer test cannot run")
    harness = tmp_path / "audio_engine_harness_sanitized.c"
    executable = tmp_path / "audio_engine_harness_sanitized"
    harness.write_text(HARNESS, encoding="utf-8")
    command = [
        compiler, "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
        "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wconversion",
        "-Wsign-conversion", "-pedantic", "-I", str(GAME_DIR), str(harness),
        str(GAME_DIR / "audio_engine.c"), "-lm", "-o", str(executable),
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)
    env = os.environ.copy()
    env.setdefault("ASAN_OPTIONS", "detect_leaks=0:halt_on_error=1")
    env.setdefault("UBSAN_OPTIONS", "halt_on_error=1:print_stacktrace=1")
    subprocess.run([str(executable)], check=True, capture_output=True, text=True, env=env)
