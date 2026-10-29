from __future__ import annotations

import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
GAME_DIR = ROOT / "app/src/main/cpp/game"

HARNESS = r'''#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include "ps2_audio_bd_stream.h"

int main(void) {
    Ps2AudioBdStreamState state;
    Ps2AudioBdTransferStep step;

    assert(ps2_audio_bd_stream_begin(&state, 0x5000u, 0x1000u) == 1);
    assert(ps2_audio_bd_stream_should_read(&state) == 1);

    /* A full read is transferred at base+bytesTransferred and requests another read. */
    assert(ps2_audio_bd_stream_prepare_transfer(&state, 0x1000, &step) == 1);
    assert(step.spu_address == 0x5000u && step.byte_count == 0x1000u);
    assert(step.continue_reading_after_transfer == 1u);
    assert(ps2_audio_bd_stream_should_read(&state) == 0); /* Must complete VoiceTrans first. */
    assert(ps2_audio_bd_stream_complete_transfer(&state, 0) == 1);
    assert(state.bytes_transferred == 0x1000u);
    assert(ps2_audio_bd_stream_should_read(&state) == 1);

    /* A short read is still transferred, then ends the loop. */
    assert(ps2_audio_bd_stream_prepare_transfer(&state, 0x123, &step) == 1);
    assert(step.spu_address == 0x6000u && step.byte_count == 0x123u);
    assert(step.continue_reading_after_transfer == 0u);
    assert(ps2_audio_bd_stream_complete_transfer(&state, 0) == 1);
    assert(state.bytes_transferred == 0x1123u);
    assert(ps2_audio_bd_stream_should_read(&state) == 0);
    assert(ps2_audio_bd_stream_prepare_transfer(&state, 0, &step) == 0);

    /* EOF follows the exact same short-read exit path (zero-byte VoiceTrans step). */
    assert(ps2_audio_bd_stream_begin(&state, 0x7000u, 0x800u) == 1);
    assert(ps2_audio_bd_stream_prepare_transfer(&state, 0, &step) == 1);
    assert(step.spu_address == 0x7000u && step.byte_count == 0u);
    assert(step.continue_reading_after_transfer == 0u);
    assert(ps2_audio_bd_stream_complete_transfer(&state, 0) == 1);
    assert(state.bytes_transferred == 0u && ps2_audio_bd_stream_should_read(&state) == 0);

    /* Invalid reads and unsuccessful SPU transfers stop without committing byte counts. */
    assert(ps2_audio_bd_stream_begin(&state, 0x1000u, 64u) == 1);
    assert(ps2_audio_bd_stream_prepare_transfer(&state, -1, &step) == 0);
    assert(state.bytes_transferred == 0u && ps2_audio_bd_stream_should_read(&state) == 1);
    assert(ps2_audio_bd_stream_prepare_transfer(&state, 65, &step) == 0);
    assert(ps2_audio_bd_stream_prepare_transfer(&state, 64, &step) == 1);
    assert(ps2_audio_bd_stream_complete_transfer(&state, -1) == 0);
    assert(state.bytes_transferred == 0u && ps2_audio_bd_stream_should_read(&state) == 0);

    /* Reject address and byte-count overflow before exposing a transfer step. */
    assert(ps2_audio_bd_stream_begin(&state, UINT32_MAX - 2u, 8u) == 1);
    assert(ps2_audio_bd_stream_prepare_transfer(&state, 4, &step) == 0);
    assert(step.byte_count == 0u);
    assert(ps2_audio_bd_stream_begin(&state, 0x1000u, 8u) == 1);
    state.bytes_transferred = UINT32_MAX - 2u;
    assert(ps2_audio_bd_stream_prepare_transfer(&state, 4, &step) == 0);
    assert(step.byte_count == 0u);

    assert(ps2_audio_bd_stream_begin(&state, 0u, 0u) == 0);
    puts("ps2_audio_bd_stream: ok");
    return 0;
}
'''


def test_bd_stream_model_matches_iop_chunk_loop() -> None:
    import tempfile

    with tempfile.TemporaryDirectory(prefix="ps2_audio_bd_stream_") as temp_dir:
        temp = pathlib.Path(temp_dir)
        source = temp / "harness.c"
        executable = temp / "harness"
        source.write_text(HARNESS, encoding="utf-8")
        subprocess.run(
            ["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wconversion",
             "-Wsign-conversion", "-pedantic", "-I", str(GAME_DIR), str(source),
             str(GAME_DIR / "ps2_audio_bd_stream.c"), "-o", str(executable)],
            check=True, capture_output=True, text=True,
        )
        result = subprocess.run([str(executable)], check=True, capture_output=True, text=True)
        assert "ps2_audio_bd_stream: ok" in result.stdout
