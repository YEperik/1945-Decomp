from __future__ import annotations

import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
GAME_DIR = ROOT / "app/src/main/cpp/game"

HARNESS = r'''#include <assert.h>
#include <stdint.h>
#include "ps2_audio_control.h"

typedef struct TestContext {
    int same_sequence_calls;
    int gate_is_zero;
    int selection_calls;
    int32_t selected_id;
} TestContext;

static void refresh_same_sequence(void *opaque) {
    TestContext *ctx = (TestContext *)opaque;
    ctx->same_sequence_calls += 1;
}

static void select_sequence(void *opaque, int32_t sequence_id) {
    TestContext *ctx = (TestContext *)opaque;
    ctx->selection_calls += 1;
    ctx->selected_id = sequence_id;
}

static int transition_gate_is_zero(void *opaque) {
    TestContext *ctx = (TestContext *)opaque;
    return ctx->gate_is_zero;
}

int main(void) {
    Ps2AudioControlCallbacks callbacks = {
        refresh_same_sequence, select_sequence, transition_gate_is_zero
    };
    TestContext ctx = {0, 0, 0, -1};
    Ps2AudioControlState state = {13, 0, 0};

    assert(ps2_audio_sequence_id_for_mode(0x04u, 0) == 1);
    assert(ps2_audio_sequence_id_for_mode(0x04u, 7) == 8);
    assert(ps2_audio_sequence_id_for_mode(0x04u, 8) == 1);
    assert(ps2_audio_sequence_id_for_mode(0x04u, 15) == 8);
    assert(ps2_audio_sequence_id_for_mode(0x04u, -1) == 0);
    assert(ps2_audio_sequence_id_for_mode(0x08u, 0) == 14);
    assert(ps2_audio_sequence_id_for_mode(0x10u, 0) == 14);
    assert(ps2_audio_sequence_id_for_mode(0x40u, 0) == 0);
    assert(ps2_audio_sequence_id_for_mode(0x80u, 0) == 17);
    assert(ps2_audio_sequence_id_for_mode(0x100u, 0) == 0);
    assert(ps2_audio_sequence_id_for_mode(0x400u, 0) == 16);
    assert(ps2_audio_sequence_id_for_mode(0x1000u, 0) == 0);
    assert(ps2_audio_sequence_id_for_mode(0x20000u, 0) == 15);
    assert(ps2_audio_sequence_id_for_mode(0x40000u, 0) == 14);
    assert(ps2_audio_sequence_id_for_mode(0x1234u, 0) == 0);

    /* 0x20: unknown/zero sequence mapping falls back to sequence 15. */
    ps2_audio_request_stage_sequence(&state, 0x40u, 0, &callbacks, &ctx);
    assert(state.target_sequence_id == 15);
    assert(state.pending == 1u);
    assert(state.current_sequence_id == 13);

    /* A nonzero raw FUN_001037C8 result means keep waiting. */
    ctx.gate_is_zero = 0;
    ps2_audio_service_pending(&state, &callbacks, &ctx);
    assert(state.pending == 1u);
    assert(ctx.selection_calls == 0);

    /* Raw gate zero triggers sequence selection and commits IDs. */
    ctx.gate_is_zero = 1;
    ps2_audio_service_pending(&state, &callbacks, &ctx);
    assert(state.pending == 0u);
    assert(state.current_sequence_id == 15);
    assert(ctx.selection_calls == 1);
    assert(ctx.selected_id == 15);

    /* Same-target branch invokes refresh and leaves pending unchanged. */
    state.pending = 1u;
    ps2_audio_request_stage_sequence(&state, 0x20000u, 0, &callbacks, &ctx);
    assert(ctx.same_sequence_calls == 1);
    assert(state.target_sequence_id == 15);
    assert(state.pending == 1u);

    /* Pending is cleared without a callback when current already equals target. */
    ps2_audio_service_pending(&state, &callbacks, &ctx);
    assert(state.pending == 0u);
    assert(ctx.selection_calls == 1);

    /* A pending request for another ID is not committed without a gate callback. */
    state.current_sequence_id = 14;
    state.target_sequence_id = 16;
    state.pending = 1u;
    ps2_audio_service_pending(&state, 0, &ctx);
    assert(state.pending == 1u);
    assert(state.current_sequence_id == 14);

    ps2_audio_request_stage_sequence(0, 0x10u, 0, &callbacks, &ctx);
    ps2_audio_service_pending(0, &callbacks, &ctx);
    return 0;
}
'''


def test_evidence_backed_ps2_audio_control_state_machine(tmp_path: pathlib.Path) -> None:
    source = tmp_path / "ps2_audio_control_harness.c"
    executable = tmp_path / "ps2_audio_control_harness"
    source.write_text(HARNESS, encoding="utf-8")
    subprocess.run(
        ["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wconversion",
         "-Wsign-conversion", "-pedantic", "-I", str(GAME_DIR), str(source),
         str(GAME_DIR / "ps2_audio_control.c"), "-o", str(executable)],
        check=True, capture_output=True, text=True,
    )
    subprocess.run([str(executable)], check=True, capture_output=True, text=True)
