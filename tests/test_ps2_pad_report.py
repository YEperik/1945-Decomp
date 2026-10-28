"""Regression tests for the narrow input-record model from supplied R5900 code."""
from __future__ import annotations

import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
MODEL_C = ROOT / "tools/reference_model/ps2_pad_report.c"
MODEL_H = ROOT / "tools/reference_model/ps2_pad_report.h"

HARNESS = r'''#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include "ps2_pad_report.h"

int main(void) {
    Ps2PadRecord r = {0};
    uint8_t p[8] = {0x00, 0x5a, 0xff, 0xfe, 0x80, 0x80, 0x80, 0x80};

    assert(sizeof(Ps2PadRecord) == 0x140);
    assert(offsetof(Ps2PadRecord, current_pressed) == 0x14);
    assert(offsetof(Ps2PadRecord, pressed_edges) == 0x18);
    assert(offsetof(Ps2PadRecord, axis_b_x) == 0x20);
    assert(offsetof(Ps2PadRecord, axis_a_x) == 0x28);
    assert(offsetof(Ps2PadRecord, device_context) == 0x40);

    /* Valid status byte 0; return and store packet byte 1 as the code does. */
    assert(ps2_pad_process_report(&r, 8, p) == 0x5a);
    assert(r.report_byte_1 == 0x5a);
    assert(r.current_pressed == 0x0001);
    assert(r.previous_pressed == 0x0000);
    assert(r.pressed_edges == 0x0001);
    assert(r.current_axis_directions == 0);
    assert(r.axis_direction_edges == 0);

    /* Held button: current persists, only the transition edge clears. */
    assert(ps2_pad_process_report(&r, 8, p) == 0x5a);
    assert(r.current_pressed == 0x0001);
    assert(r.previous_pressed == 0x0001);
    assert(r.pressed_edges == 0);

    /* Release: no new-press edge. */
    p[3] = 0xff;
    assert(ps2_pad_process_report(&r, 8, p) == 0x5a);
    assert(r.current_pressed == 0);
    assert(r.previous_pressed == 1);
    assert(r.pressed_edges == 0);

    /* Byte order: packet[2] feeds the high half of the active-low mask. */
    p[2] = 0xfe;
    p[3] = 0xff;
    assert(ps2_pad_process_report(&r, 8, p) == 0x5a);
    assert(r.current_pressed == 0x0100);
    assert(r.pressed_edges == 0x0100);

    /* Signed axis boundary values (-64/+64) produce exact numeric masks. */
    p[2] = 0xff; p[3] = 0xff;
    p[4] = 0x40; p[5] = 0xc0; p[6] = 0xc0; p[7] = 0x40;
    assert(ps2_pad_process_report(&r, 8, p) == 0x5a);
    assert(r.axis_a_x == -64);
    assert(r.axis_a_y == 64);
    assert(r.axis_b_x == 64);
    assert(r.axis_b_y == -64);
    assert(r.current_axis_directions == 0x0096);
    assert(r.previous_axis_directions == 0);
    assert(r.axis_direction_edges == 0x0096);

    /* Opposite extrema cover the complementary four direction masks. */
    p[4] = 0xc0; p[5] = 0x40; p[6] = 0x40; p[7] = 0xc0;
    assert(ps2_pad_process_report(&r, 8, p) == 0x5a);
    assert(r.current_axis_directions == 0x0069);
    assert(r.previous_axis_directions == 0x0096);
    assert(r.axis_direction_edges == 0x0069);

    /* Boundary-adjacent (-63/+63) remains neutral. */
    p[4] = 0x41; p[5] = 0xbf; p[6] = 0xbf; p[7] = 0x41;
    assert(ps2_pad_process_report(&r, 8, p) == 0x5a);
    assert(r.current_axis_directions == 0);
    assert(r.previous_axis_directions == 0x0069);
    assert(r.axis_direction_edges == 0);

    /* Button mask 0xf000 suppresses axis-B values; semantic button names unknown. */
    p[2] = 0x0f; p[3] = 0xff;
    p[4] = 0x80; p[5] = 0x80; p[6] = 0xc0; p[7] = 0x40;
    assert(ps2_pad_process_report(&r, 8, p) == 0x5a);
    assert(r.current_pressed == 0xf000);
    assert(r.axis_b_x == 0);
    assert(r.axis_b_y == 0);
    assert((r.current_axis_directions & 0x00f0) == 0);

    /* All four raw axes == 0 is a sentinel; axis-derived state gets reset. */
    r.current_axis_directions = 0x0096;
    p[2] = 0xff; p[3] = 0xfe;
    p[4] = 0; p[5] = 0; p[6] = 0; p[7] = 0;
    assert(ps2_pad_process_report(&r, 8, p) == 0x5a);
    assert(r.current_pressed == 1);
    assert(r.pressed_edges == 1);
    assert(r.axis_a_x == 0 && r.axis_a_y == 0);
    assert(r.axis_b_x == 0 && r.axis_b_y == 0);
    assert(r.current_axis_directions == 0);
    assert(r.previous_axis_directions == 0);
    assert(r.axis_direction_edges == 0);

    /* Reset path clears exactly the input fields but preserves unrelated fields. */
    r.port = 1; r.slot = 0; r.report_byte_1 = 0x5a;
    r.state_0c = 3; r.state_10 = 4;
    r.reserved_30[0] = 0x77;
    r.device_context[0] = 0x99;
    r.current_pressed = 1; r.previous_pressed = 2; r.pressed_edges = 3;
    r.current_axis_directions = 0x96; r.previous_axis_directions = 0x86;
    r.axis_direction_edges = 0x10;
    r.axis_a_x = -64; r.axis_a_y = 64; r.axis_b_x = -64; r.axis_b_y = 64;
    assert(ps2_pad_process_report(&r, 0, p) == 0);
    assert(r.current_pressed == 0 && r.previous_pressed == 0 && r.pressed_edges == 0);
    assert(r.current_axis_directions == 0 && r.previous_axis_directions == 0);
    assert(r.axis_direction_edges == 0);
    assert(r.axis_a_x == 0 && r.axis_a_y == 0 && r.axis_b_x == 0 && r.axis_b_y == 0);
    assert(r.port == 1 && r.slot == 0 && r.report_byte_1 == 0x5a);
    assert(r.state_0c == 3 && r.state_10 == 4);
    assert(r.reserved_30[0] == 0x77 && r.device_context[0] == 0x99);

    /* The binary checks read_result only for zero, not minimum packet length.
       This uses a fully-backed eight-byte array and records behavior, not a
       claim that a one-byte native transfer is safe or valid hardware output. */
    p[0] = 0; p[1] = 0x5a; p[2] = 0xff; p[3] = 0xfe;
    p[4] = 0x80; p[5] = 0x80; p[6] = 0x80; p[7] = 0x80;
    assert(ps2_pad_process_report(&r, 1, p) == 0x5a);
    assert(r.current_pressed == 1);

    /* Nonzero status byte also takes reset path and does not store packet[1]. */
    r.current_pressed = 0x1234;
    p[0] = 1; p[1] = 0xa5;
    assert(ps2_pad_process_report(&r, 8, p) == 0);
    assert(r.current_pressed == 0 && r.pressed_edges == 0);
    assert(r.report_byte_1 == 0x5a);

    /* Null record is handled defensively by the model. */
    assert(ps2_pad_process_report(NULL, false, NULL) == 0);
    return 0;
}
'''


def test_ps2_pad_full_report_model(tmp_path: pathlib.Path) -> None:
    compiler = "cc"
    exe = tmp_path / "test_ps2_pad_report"
    harness = tmp_path / "harness.c"
    harness.write_text(HARNESS, encoding="utf-8")
    subprocess.run(
        [compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
         "-I", str(MODEL_H.parent), str(harness), str(MODEL_C), "-o", str(exe)],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run([str(exe)], check=True, capture_output=True, text=True)
