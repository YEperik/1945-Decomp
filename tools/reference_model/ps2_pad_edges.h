#ifndef PS2_PAD_EDGES_H
#define PS2_PAD_EDGES_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Minimal source-level model of the successful digital-button update path in
 * Ghidra export SLES_517.41.c, FUN_00187a40.
 *
 * raw_first/raw_second are supplied in the same order used by CONCAT11 in the
 * decompiler export. The original code treats the resulting 16-bit field as
 * active-low and complements it. This model does not cover pad read failures,
 * device-type dispatch, analog axes, or PS2 runtime integration.
 */
typedef struct Ps2PadDigitalEdges {
    uint16_t previous_pressed;
    uint16_t current_pressed;
    uint16_t pressed_edges;
} Ps2PadDigitalEdges;

/* State must be zero-initialized to model the cleared startup state. */
void ps2_pad_update_digital(Ps2PadDigitalEdges *state,
                            uint8_t raw_first,
                            uint8_t raw_second);

#ifdef __cplusplus
}
#endif

#endif
