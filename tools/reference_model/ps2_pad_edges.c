#include "ps2_pad_edges.h"

void ps2_pad_update_digital(Ps2PadDigitalEdges *state,
                            uint8_t raw_first,
                            uint8_t raw_second)
{
    const uint16_t raw_active_low =
        (uint16_t)(((uint16_t)raw_first << 8) | (uint16_t)raw_second);
    const uint16_t now_pressed = (uint16_t)~raw_active_low;
    const uint16_t old_pressed = state->current_pressed;

    /* Mirrors the ordering observed in FUN_00187a40:
       edge = new active bits & ~old active bits; preserve old; then store new. */
    state->pressed_edges = (uint16_t)(now_pressed & (uint16_t)~old_pressed);
    state->previous_pressed = old_pressed;
    state->current_pressed = now_pressed;
}
