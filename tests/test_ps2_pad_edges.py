"""Compile and exercise the small C model derived from the Ghidra export."""
from __future__ import annotations

import pathlib
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MODEL_C = ROOT / "tools/reference_model/ps2_pad_edges.c"
MODEL_H = ROOT / "tools/reference_model/ps2_pad_edges.h"

HARNESS = r'''#include <assert.h>
#include <stdint.h>
#include "ps2_pad_edges.h"

int main(void) {
    Ps2PadDigitalEdges s = {0, 0, 0};

    /* No buttons pressed: raw active-low bits all set. */
    ps2_pad_update_digital(&s, 0xff, 0xff);
    assert(s.previous_pressed == 0x0000);
    assert(s.current_pressed == 0x0000);
    assert(s.pressed_edges == 0x0000);

    /* A single bit becomes active: it appears in current and edge masks. */
    ps2_pad_update_digital(&s, 0xff, 0xfe);
    assert(s.previous_pressed == 0x0000);
    assert(s.current_pressed == 0x0001);
    assert(s.pressed_edges == 0x0001);

    /* Holding the same bit does not produce another press edge. */
    ps2_pad_update_digital(&s, 0xff, 0xfe);
    assert(s.previous_pressed == 0x0001);
    assert(s.current_pressed == 0x0001);
    assert(s.pressed_edges == 0x0000);

    /* Releasing it produces no press edge; this source path has no release mask. */
    ps2_pad_update_digital(&s, 0xff, 0xff);
    assert(s.previous_pressed == 0x0001);
    assert(s.current_pressed == 0x0000);
    assert(s.pressed_edges == 0x0000);

    /* Switching to another bit yields an edge only for the newly active bit. */
    ps2_pad_update_digital(&s, 0xff, 0xfd);
    assert(s.previous_pressed == 0x0000);
    assert(s.current_pressed == 0x0002);
    assert(s.pressed_edges == 0x0002);

    /* Two newly active bits are preserved independently. */
    ps2_pad_update_digital(&s, 0xff, 0xf3);
    assert(s.previous_pressed == 0x0002);
    assert(s.current_pressed == 0x000c);
    assert(s.pressed_edges == 0x000c);

    /* CONCAT11 places raw_first in the high byte: verify the 0x0100 bit. */
    s = (Ps2PadDigitalEdges){0, 0, 0};
    ps2_pad_update_digital(&s, 0xfe, 0xff);
    assert(s.previous_pressed == 0x0000);
    assert(s.current_pressed == 0x0100);
    assert(s.pressed_edges == 0x0100);

    return 0;
}
'''


def test_ps2_pad_edge_model(tmp_path: pathlib.Path) -> None:
    compiler = "cc"
    exe = tmp_path / "test_ps2_pad_edges"
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
