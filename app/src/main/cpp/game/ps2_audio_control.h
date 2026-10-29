#ifndef PORT1945_PS2_AUDIO_CONTROL_H
#define PORT1945_PS2_AUDIO_CONTROL_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Evidence-backed slice of the PS2 audio control path reconstructed from
 * SLES_517.41 R5900 listing addresses 0x00101940, 0x00101AC8 and 0x00101E58.
 * This models sequence selection/state only. It does not decode MIDI or play
 * original audio, and it is not yet connected to the authored game prototype.
 */
typedef struct Ps2AudioControlState {
    int32_t current_sequence_id; /* corresponds to DAT_003353B4 */
    int32_t target_sequence_id;  /* corresponds to DAT_003353B0 */
    uint8_t pending;             /* corresponds to DAT_003353B8 */
} Ps2AudioControlState;

typedef struct Ps2AudioControlCallbacks {
    /* Called on the 0x20 command when the requested ID already is current. */
    void (*refresh_same_sequence)(void *context);
    /* Called after the deferred gate allows FUN_001016E0(target_sequence_id). */
    void (*select_sequence)(void *context, int32_t target_sequence_id);
    /* Must return nonzero when FUN_001037C8() returns zero in the PS2 path. */
    int (*transition_gate_is_zero)(void *context);
} Ps2AudioControlCallbacks;

/*
 * Mirrors the mode-to-sequence mapping visible in FUN_00101940.
 * For mode 0x04, the listing normalizes the helper result using the equivalent
 * of C signed remainder by 8, then adds 1. The stage-BGM command later maps a
 * zero result to sequence 15.
 */
int32_t ps2_audio_sequence_id_for_mode(uint32_t game_mode,
                                       int32_t selected_player_index);

/* Mirrors the BGM_STAGE command (0x20) branch in FUN_00101AC8. */
void ps2_audio_request_stage_sequence(Ps2AudioControlState *state,
                                      uint32_t game_mode,
                                      int32_t selected_player_index,
                                      const Ps2AudioControlCallbacks *callbacks,
                                      void *context);

/* Mirrors the deferred-transition checks in FUN_00101E58. */
void ps2_audio_service_pending(Ps2AudioControlState *state,
                               const Ps2AudioControlCallbacks *callbacks,
                               void *context);

#ifdef __cplusplus
}
#endif

#endif
