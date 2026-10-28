#ifndef PS2_PAD_REPORT_H
#define PS2_PAD_REPORT_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Memory-layout model of the 0x140-byte record used by the input path.
 * Field names are numeric/functional labels from the observed instructions;
 * they deliberately avoid unverified canonical PS2 button/axis names.
 */
typedef struct Ps2PadRecord {
    uint32_t port;                       /* +0x00 */
    uint32_t slot;                       /* +0x04 */
    uint32_t report_byte_1;              /* +0x08: packet byte 1 copied as a word */
    uint32_t state_0c;                   /* +0x0c: handled by separate state machine */
    uint32_t state_10;                   /* +0x10: handled by separate state machine */
    uint16_t current_pressed;            /* +0x14 */
    uint16_t previous_pressed;           /* +0x16 */
    uint16_t pressed_edges;              /* +0x18 */
    uint16_t current_axis_directions;    /* +0x1a */
    uint16_t previous_axis_directions;   /* +0x1c */
    uint16_t axis_direction_edges;       /* +0x1e */
    int32_t axis_b_x;                    /* +0x20: packet byte 6 - 0x80 */
    int32_t axis_b_y;                    /* +0x24: packet byte 7 - 0x80 */
    int32_t axis_a_x;                    /* +0x28: packet byte 4 - 0x80 */
    int32_t axis_a_y;                    /* +0x2c: packet byte 5 - 0x80 */
    uint8_t reserved_30[0x10];           /* +0x30 .. +0x3f */
    uint8_t device_context[0x100];       /* +0x40 .. +0x13f */
} Ps2PadRecord;

/*
 * Mirrors FUN_00187890's reset scope: digital masks and axis-derived fields
 * are zeroed; port/slot, report byte, state-machine words and opaque storage
 * are not touched by the shown reset helpers.
 */
void ps2_pad_reset_input_fields(Ps2PadRecord *record);

/*
 * Model of the successful/failed read branches in FUN_00187a40.
 * `read_result` is the byte count returned by FUN_001b4460; the machine code
 * branches only on zero/nonzero, not on a minimum length. packet points to an
 * eight-byte backing buffer. Returns packet[1] on the parsed path, or zero after
 * a reset path, as seen at FUN_00187c20. The nonzero-short-read behavior is
 * represented for fidelity but must not be treated as a safe native API contract.
 */
uint32_t ps2_pad_process_report(Ps2PadRecord *record,
                                uint32_t read_result,
                                const uint8_t packet[8]);

/* Direct native-input bridge. `buttons_mask` is already active-high in the
 * game's numeric bit layout; axis order is A-X, A-Y, B-X, B-Y in signed
 * centered units [-128,127]. This updates only input-derived fields and does
 * not emulate the original API report/status state machine. `connected=false`
 * follows the observed reset-helper scope. Returns 1 for an applied sample,
 * 0 when disconnected/invalid. */
uint32_t ps2_pad_apply_native_sample(Ps2PadRecord *record,
                                     uint16_t buttons_mask,
                                     const int16_t axes[4],
                                     bool connected);

#ifdef __cplusplus
}
#endif

#endif
