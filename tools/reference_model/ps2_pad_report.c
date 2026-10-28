#include "ps2_pad_report.h"

#include <stddef.h>

_Static_assert(offsetof(Ps2PadRecord, port) == 0x00, "port offset mismatch");
_Static_assert(offsetof(Ps2PadRecord, slot) == 0x04, "slot offset mismatch");
_Static_assert(offsetof(Ps2PadRecord, report_byte_1) == 0x08, "report offset mismatch");
_Static_assert(offsetof(Ps2PadRecord, current_pressed) == 0x14, "current buttons offset mismatch");
_Static_assert(offsetof(Ps2PadRecord, previous_pressed) == 0x16, "previous buttons offset mismatch");
_Static_assert(offsetof(Ps2PadRecord, pressed_edges) == 0x18, "button edge offset mismatch");
_Static_assert(offsetof(Ps2PadRecord, current_axis_directions) == 0x1a, "axis directions offset mismatch");
_Static_assert(offsetof(Ps2PadRecord, previous_axis_directions) == 0x1c, "previous axis directions offset mismatch");
_Static_assert(offsetof(Ps2PadRecord, axis_direction_edges) == 0x1e, "axis edge offset mismatch");
_Static_assert(offsetof(Ps2PadRecord, axis_b_x) == 0x20, "axis B X offset mismatch");
_Static_assert(offsetof(Ps2PadRecord, axis_b_y) == 0x24, "axis B Y offset mismatch");
_Static_assert(offsetof(Ps2PadRecord, axis_a_x) == 0x28, "axis A X offset mismatch");
_Static_assert(offsetof(Ps2PadRecord, axis_a_y) == 0x2c, "axis A Y offset mismatch");
_Static_assert(offsetof(Ps2PadRecord, device_context) == 0x40, "device context offset mismatch");
_Static_assert(sizeof(Ps2PadRecord) == 0x140, "record stride mismatch");

static void reset_axis_fields(Ps2PadRecord *record)
{
    record->current_axis_directions = 0;
    record->previous_axis_directions = 0;
    record->axis_direction_edges = 0;
    record->axis_b_x = 0;
    record->axis_b_y = 0;
    record->axis_a_x = 0;
    record->axis_a_y = 0;
}

void ps2_pad_reset_input_fields(Ps2PadRecord *record)
{
    if (record == NULL) {
        return;
    }

    record->current_pressed = 0;
    record->previous_pressed = 0;
    record->pressed_edges = 0;
    reset_axis_fields(record);
}

static void add_axis_direction(int32_t value,
                               uint16_t negative_mask,
                               uint16_t positive_mask,
                               uint16_t *directions)
{
    /* SLTI comparisons observed: value < -0x3f, then value >= 0x40. */
    if (value < -63) {
        *directions = (uint16_t)(*directions | negative_mask);
    } else if (value >= 64) {
        *directions = (uint16_t)(*directions | positive_mask);
    }
}

uint32_t ps2_pad_process_report(Ps2PadRecord *record,
                                uint32_t read_result,
                                const uint8_t packet[8])
{
    uint16_t old_pressed;
    uint16_t old_axis_directions;
    uint16_t raw_active_low;
    uint16_t now_pressed;
    bool no_axis_data;

    if (record == NULL) {
        return 0;
    }
    if (read_result == 0 || packet == NULL || packet[0] != 0) {
        ps2_pad_reset_input_fields(record);
        return 0;
    }

    old_pressed = record->current_pressed;
    old_axis_directions = record->current_axis_directions;

    /* Assembly forms (packet[2] << 8) | packet[3], then NORs it. */
    raw_active_low = (uint16_t)(((uint16_t)packet[2] << 8) | packet[3]);
    now_pressed = (uint16_t)~raw_active_low;
    record->previous_pressed = old_pressed;
    record->current_pressed = now_pressed;
    record->pressed_edges = (uint16_t)(now_pressed & (uint16_t)~old_pressed);
    record->previous_axis_directions = old_axis_directions;
    record->report_byte_1 = packet[1];

    record->axis_a_x = (int32_t)packet[4] - 0x80;
    record->axis_a_y = (int32_t)packet[5] - 0x80;
    record->axis_b_x = (int32_t)packet[6] - 0x80;
    record->axis_b_y = (int32_t)packet[7] - 0x80;

    /* If all four raw axis bytes are zero, FUN_00187870 clears axis fields. */
    no_axis_data = packet[4] == 0 && packet[5] == 0 &&
                   packet[6] == 0 && packet[7] == 0;
    if (no_axis_data) {
        reset_axis_fields(record);
    } else {
        /* Exact numeric mask from 0x00187b28; semantic button names unknown. */
        if ((record->current_pressed & 0xf000u) != 0) {
            record->axis_b_x = 0;
            record->axis_b_y = 0;
        }

        record->current_axis_directions = 0;
        add_axis_direction(record->axis_a_x, 0x02, 0x01,
                           &record->current_axis_directions);
        add_axis_direction(record->axis_a_y, 0x08, 0x04,
                           &record->current_axis_directions);
        add_axis_direction(record->axis_b_x, 0x20, 0x10,
                           &record->current_axis_directions);
        add_axis_direction(record->axis_b_y, 0x80, 0x40,
                           &record->current_axis_directions);
    }

    record->axis_direction_edges = (uint16_t)(
        record->current_axis_directions &
        (uint16_t)~record->previous_axis_directions);

    return packet[1];
}

static int32_t clamp_centered_axis(int16_t value)
{
    if (value < -128) {
        return -128;
    }
    if (value > 127) {
        return 127;
    }
    return value;
}

uint32_t ps2_pad_apply_native_sample(Ps2PadRecord *record,
                                     uint16_t buttons_mask,
                                     const int16_t axes[4],
                                     bool connected)
{
    uint16_t old_pressed;
    uint16_t old_axis_directions;

    if (record == NULL) {
        return 0;
    }
    if (!connected || axes == NULL) {
        ps2_pad_reset_input_fields(record);
        return 0;
    }

    old_pressed = record->current_pressed;
    old_axis_directions = record->current_axis_directions;

    record->previous_pressed = old_pressed;
    record->current_pressed = buttons_mask;
    record->pressed_edges = (uint16_t)(buttons_mask & (uint16_t)~old_pressed);
    record->previous_axis_directions = old_axis_directions;

    /* Keep native callers inside the byte-minus-0x80 range of the target. */
    record->axis_a_x = clamp_centered_axis(axes[0]);
    record->axis_a_y = clamp_centered_axis(axes[1]);
    record->axis_b_x = clamp_centered_axis(axes[2]);
    record->axis_b_y = clamp_centered_axis(axes[3]);

    /* Match the numeric 0xf000 gate from the original report path. */
    if ((record->current_pressed & 0xf000u) != 0) {
        record->axis_b_x = 0;
        record->axis_b_y = 0;
    }

    record->current_axis_directions = 0;
    add_axis_direction(record->axis_a_x, 0x02, 0x01,
                       &record->current_axis_directions);
    add_axis_direction(record->axis_a_y, 0x08, 0x04,
                       &record->current_axis_directions);
    add_axis_direction(record->axis_b_x, 0x20, 0x10,
                       &record->current_axis_directions);
    add_axis_direction(record->axis_b_y, 0x80, 0x40,
                       &record->current_axis_directions);
    record->axis_direction_edges = (uint16_t)(
        record->current_axis_directions & (uint16_t)~old_axis_directions);

    return 1;
}
