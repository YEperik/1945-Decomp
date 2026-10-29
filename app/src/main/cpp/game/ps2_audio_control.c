#include "ps2_audio_control.h"

#include <stddef.h>

#define PS2_AUDIO_FALLBACK_SEQUENCE_ID 15

int32_t ps2_audio_sequence_id_for_mode(uint32_t game_mode,
                                       int32_t selected_player_index)
{
    switch (game_mode) {
        case 0x00000004u:
            return (selected_player_index % 8) + 1;
        case 0x00000008u:
        case 0x00000010u:
        case 0x00040000u:
            return 14;
        case 0x00000080u:
            return 17;
        case 0x00000400u:
            return 16;
        case 0x00020000u:
            return 15;
        case 0x00000040u:
        case 0x00000100u:
        case 0x00001000u:
        default:
            return 0;
    }
}

void ps2_audio_request_stage_sequence(Ps2AudioControlState *state,
                                      uint32_t game_mode,
                                      int32_t selected_player_index,
                                      const Ps2AudioControlCallbacks *callbacks,
                                      void *context)
{
    int32_t target_sequence_id;

    if (state == NULL) {
        return;
    }

    target_sequence_id = ps2_audio_sequence_id_for_mode(game_mode,
                                                        selected_player_index);
    if (target_sequence_id == 0) {
        target_sequence_id = PS2_AUDIO_FALLBACK_SEQUENCE_ID;
    }
    state->target_sequence_id = target_sequence_id;

    if (state->current_sequence_id == target_sequence_id) {
        /* The PS2 branch invokes the same-sequence refresh calls and returns;
         * it does not write DAT_003353B8 in this branch. Preserve pending. */
        if (callbacks != NULL && callbacks->refresh_same_sequence != NULL) {
            callbacks->refresh_same_sequence(context);
        }
        return;
    }

    state->pending = 1u;
}

void ps2_audio_service_pending(Ps2AudioControlState *state,
                               const Ps2AudioControlCallbacks *callbacks,
                               void *context)
{
    int gate_is_zero;

    if (state == NULL || state->pending == 0u) {
        return;
    }

    if (state->current_sequence_id == state->target_sequence_id) {
        state->pending = 0u;
        return;
    }

    if (callbacks == NULL || callbacks->transition_gate_is_zero == NULL) {
        return;
    }
    gate_is_zero = callbacks->transition_gate_is_zero(context);
    if (gate_is_zero == 0) {
        return;
    }

    if (callbacks->select_sequence != NULL) {
        callbacks->select_sequence(context, state->target_sequence_id);
    }
    state->pending = 0u;
    state->current_sequence_id = state->target_sequence_id;
}
