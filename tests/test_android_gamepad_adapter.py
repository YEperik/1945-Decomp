"""Portable regression tests for Android event normalization and pad-state bridging."""
from __future__ import annotations

import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
ADAPTER_C = ROOT / "tools/reference_model/android_gamepad_adapter.c"
ADAPTER_H = ROOT / "tools/reference_model/android_gamepad_adapter.h"
PAD_C = ROOT / "tools/reference_model/ps2_pad_report.c"
PAD_H = ROOT / "tools/reference_model/ps2_pad_report.h"

HARNESS = r'''#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <string.h>
#include "android_gamepad_adapter.h"
#include "ps2_pad_report.h"

static uint32_t next_random(uint32_t *state) {
    *state = (*state * 1664525u) + 1013904223u;
    return *state;
}

static int32_t clamp_axis_for_expected(int16_t value) {
    if (value < -128) return -128;
    if (value > 127) return 127;
    return value;
}

static uint16_t expected_directions(uint16_t buttons, const int16_t input[4]) {
    int32_t ax = clamp_axis_for_expected(input[0]);
    int32_t ay = clamp_axis_for_expected(input[1]);
    int32_t bx = clamp_axis_for_expected(input[2]);
    int32_t by = clamp_axis_for_expected(input[3]);
    uint16_t result = 0;
    if ((buttons & 0xf000u) != 0) { bx = 0; by = 0; }
    if (ax < -63) result |= 0x02;
    if (ax >= 64) result |= 0x01;
    if (ay < -63) result |= 0x08;
    if (ay >= 64) result |= 0x04;
    if (bx < -63) result |= 0x20;
    if (bx >= 64) result |= 0x10;
    if (by < -63) result |= 0x80;
    if (by >= 64) result |= 0x40;
    return result;
}

int main(void) {
    AndroidGamepadAdapter adapter;
    AndroidGamepadSample sample;
    Ps2PadRecord record = {0};
    const int16_t axes_full[4] = {-64, 64, -64, 64};
    const int16_t axes_neutral[4] = {0, 0, 0, 0};

    agp_init(&adapter);
    agp_read_sample(&adapter, &sample);
    assert(!sample.connected && sample.buttons_mask == 0);

    /* Mapping is configured by the caller; there are deliberately no defaults. */
    assert(agp_bind_key(&adapter, 100, 0x0001));
    assert(agp_bind_key(&adapter, 101, 0x0001));
    assert(agp_bind_key(&adapter, 102, 0x2000));
    assert(agp_bind_key(&adapter, 104, 0x0002));
    assert(agp_bind_axis(&adapter, 10, AGP_AXIS_A_X));
    assert(agp_bind_axis(&adapter, 11, AGP_AXIS_A_Y));
    assert(agp_bind_axis(&adapter, 12, AGP_AXIS_B_X));
    assert(agp_bind_axis(&adapter, 13, AGP_AXIS_B_Y));
    assert(agp_bind_hat_axis(&adapter, 14, 0x0002, 0x0004));
    assert(!agp_bind_key(&adapter, 103, 0));
    assert(!agp_bind_hat_axis(&adapter, 15, 0, 0));

    assert(!agp_on_key(&adapter, 100, true)); /* event ignored while disconnected */
    agp_set_connected(&adapter, true);
    assert(agp_on_key(&adapter, 100, true));
    assert(agp_on_key(&adapter, 100, true)); /* repeated DOWN is idempotent */
    assert(agp_on_key(&adapter, 101, true));
    assert(agp_on_key(&adapter, 100, false));
    agp_read_sample(&adapter, &sample);
    assert(sample.connected && sample.buttons_mask == 0x0001);
    assert(agp_on_key(&adapter, 101, false));
    agp_read_sample(&adapter, &sample);
    assert(sample.buttons_mask == 0);
    assert(!agp_on_key(&adapter, 999, true));

    /* Standardized axis normalization, including asymmetric signed endpoints. */
    assert(agp_on_axis(&adapter, 10, -1.0f));
    assert(agp_on_axis(&adapter, 11, 1.0f));
    assert(agp_on_axis(&adapter, 12, -0.5f));
    assert(agp_on_axis(&adapter, 13, 0.5f));
    agp_read_sample(&adapter, &sample);
    assert(sample.axes[0] == -128);
    assert(sample.axes[1] == 127);
    assert(sample.axes[2] == -64);
    assert(sample.axes[3] == 64);
    assert(agp_normalize_axis(NAN) == 0);
    assert(agp_normalize_axis(INFINITY) == 127);
    assert(agp_normalize_axis(-INFINITY) == -128);
    assert(!agp_on_axis(&adapter, 999, 0.75f));

    /* A hat axis can feed digital masks with the same binary thresholds. */
    assert(agp_on_axis(&adapter, 14, -0.49f));
    agp_read_sample(&adapter, &sample);
    assert((sample.buttons_mask & 0x0006) == 0);
    assert(agp_on_axis(&adapter, 14, -0.5f));
    agp_read_sample(&adapter, &sample);
    assert((sample.buttons_mask & 0x0006) == 0x0002);
    assert(agp_on_axis(&adapter, 14, 0.5f));
    agp_read_sample(&adapter, &sample);
    assert((sample.buttons_mask & 0x0006) == 0x0004);

    /* A D-pad key and a hat event sharing one output bit compose safely. */
    assert(agp_on_key(&adapter, 104, true));
    assert(agp_on_axis(&adapter, 14, -0.5f));
    assert(agp_on_key(&adapter, 104, false));
    agp_read_sample(&adapter, &sample);
    assert((sample.buttons_mask & 0x0002) == 0x0002);
    assert(agp_on_axis(&adapter, 14, 0.0f));
    agp_read_sample(&adapter, &sample);
    assert((sample.buttons_mask & 0x0006) == 0);

    /* The bridge applies only input-derived fields and preserves API state. */
    record.port = 1;
    record.slot = 0;
    record.report_byte_1 = 0x5a;
    record.state_0c = 7;
    record.state_10 = 2;
    assert(ps2_pad_apply_native_sample(&record, 0x0101, axes_full, true) == 1);
    assert(record.current_pressed == 0x0101);
    assert(record.previous_pressed == 0);
    assert(record.pressed_edges == 0x0101);
    assert(record.axis_a_x == -64 && record.axis_a_y == 64);
    assert(record.axis_b_x == -64 && record.axis_b_y == 64);
    assert(record.current_axis_directions == 0x0066);
    assert(record.axis_direction_edges == 0x0066);

    assert(ps2_pad_apply_native_sample(&record, 0x0101, axes_full, true) == 1);
    assert(record.pressed_edges == 0);
    assert(record.axis_direction_edges == 0);

    /* A numeric mask in 0xf000 suppresses the observed axis-B pair. */
    assert(ps2_pad_apply_native_sample(&record, 0x2000, axes_full, true) == 1);
    assert(record.axis_b_x == 0 && record.axis_b_y == 0);
    assert((record.current_axis_directions & 0x00f0) == 0);

    assert(ps2_pad_apply_native_sample(&record, 0, axes_neutral, true) == 1);
    assert(record.current_pressed == 0 && record.pressed_edges == 0);
    assert(record.current_axis_directions == 0);
    assert(record.axis_a_x == 0 && record.axis_a_y == 0);

    /* Clamp hostile/out-of-contract native values to the original byte range. */
    {
        const int16_t out_of_range[4] = {-300, 300, -129, 128};
        assert(ps2_pad_apply_native_sample(&record, 0, out_of_range, true) == 1);
        assert(record.axis_a_x == -128 && record.axis_a_y == 127);
        assert(record.axis_b_x == -128 && record.axis_b_y == 127);
    }

    assert(ps2_pad_apply_native_sample(&record, 0xffff, axes_full, false) == 0);
    assert(record.current_pressed == 0 && record.previous_pressed == 0);
    assert(record.pressed_edges == 0 && record.current_axis_directions == 0);
    assert(record.axis_a_x == 0 && record.axis_a_y == 0);
    assert(record.axis_b_x == 0 && record.axis_b_y == 0);
    assert(record.port == 1 && record.slot == 0);
    assert(record.report_byte_1 == 0x5a && record.state_0c == 7 && record.state_10 == 2);

    /* Disconnect releases all held adapter inputs; reconnect starts neutral. */
    assert(agp_on_key(&adapter, 102, true));
    assert(agp_on_axis(&adapter, 10, 0.8f));
    agp_set_connected(&adapter, false);
    agp_read_sample(&adapter, &sample);
    assert(!sample.connected && sample.buttons_mask == 0);
    assert(sample.axes[0] == 0 && sample.axes[1] == 0 &&
           sample.axes[2] == 0 && sample.axes[3] == 0);
    agp_set_connected(&adapter, true);
    agp_read_sample(&adapter, &sample);
    assert(sample.connected && sample.buttons_mask == 0);
    assert(sample.axes[0] == 0 && sample.axes[1] == 0 &&
           sample.axes[2] == 0 && sample.axes[3] == 0);

    /* Deterministic property sweep across mask/axis boundaries and state edges. */
    {
        uint32_t rng = 0x1945a11u;
        unsigned int i;
        for (i = 0; i < 4096u; ++i) {
            uint16_t mask = (uint16_t)next_random(&rng);
            int16_t random_axes[4];
            uint16_t old_mask = record.current_pressed;
            uint16_t old_directions = record.current_axis_directions;
            uint16_t expected_dir;
            uint32_t r0 = next_random(&rng);
            uint32_t r1 = next_random(&rng);
            uint32_t r2 = next_random(&rng);
            uint32_t r3 = next_random(&rng);
            random_axes[0] = (int16_t)((int32_t)(r0 % 801u) - 400);
            random_axes[1] = (int16_t)((int32_t)(r1 % 801u) - 400);
            random_axes[2] = (int16_t)((int32_t)(r2 % 801u) - 400);
            random_axes[3] = (int16_t)((int32_t)(r3 % 801u) - 400);
            expected_dir = expected_directions(mask, random_axes);
            assert(ps2_pad_apply_native_sample(&record, mask, random_axes, true) == 1);
            assert(record.previous_pressed == old_mask);
            assert(record.current_pressed == mask);
            assert(record.pressed_edges == (uint16_t)(mask & (uint16_t)~old_mask));
            assert(record.previous_axis_directions == old_directions);
            assert(record.current_axis_directions == expected_dir);
            assert(record.axis_direction_edges ==
                   (uint16_t)(expected_dir & (uint16_t)~old_directions));
            assert(record.axis_a_x == clamp_axis_for_expected(random_axes[0]));
            assert(record.axis_a_y == clamp_axis_for_expected(random_axes[1]));
            assert(record.axis_b_x == ((mask & 0xf000u) ? 0 :
                   clamp_axis_for_expected(random_axes[2])));
            assert(record.axis_b_y == ((mask & 0xf000u) ? 0 :
                   clamp_axis_for_expected(random_axes[3])));
        }
    }

    /* Capacity limits and invalid axis targets fail closed. */
    {
        AndroidGamepadAdapter limits;
        unsigned int i;
        agp_init(&limits);
        agp_set_connected(&limits, true);
        for (i = 0; i < AGP_MAX_KEY_BINDINGS; ++i) {
            assert(agp_bind_key(&limits, (int32_t)(2000 + i),
                                (uint16_t)(1u << (i % 16u))));
        }
        assert(!agp_bind_key(&limits, 3000, 1));
        for (i = 0; i < AGP_MAX_HAT_BINDINGS; ++i) {
            assert(agp_bind_hat_axis(&limits, (int32_t)(30 + i), 1, 2));
        }
        assert(!agp_bind_hat_axis(&limits, 40, 1, 2));
        assert(!agp_bind_axis(&limits, 50, (AgpAxisTarget)99));
    }

    /* Null-safe public entry points. */
    agp_init(NULL);
    agp_set_connected(NULL, true);
    assert(!agp_bind_key(NULL, 1, 1));
    assert(!agp_bind_axis(NULL, 1, AGP_AXIS_A_X));
    assert(!agp_bind_hat_axis(NULL, 1, 1, 0));
    assert(!agp_on_key(NULL, 1, true));
    assert(!agp_on_axis(NULL, 1, 0.0f));
    agp_read_sample(NULL, &sample);
    assert(!sample.connected && sample.buttons_mask == 0);
    return 0;
}
'''


def test_android_gamepad_adapter_and_native_bridge(tmp_path: pathlib.Path) -> None:
    exe = tmp_path / "test_android_gamepad_adapter"
    harness = tmp_path / "harness.c"
    harness.write_text(HARNESS, encoding="utf-8")
    subprocess.run(
        [
            "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
            "-I", str(ADAPTER_H.parent), "-I", str(PAD_H.parent),
            str(harness), str(ADAPTER_C), str(PAD_C), "-o", str(exe),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run([str(exe)], check=True, capture_output=True, text=True)
