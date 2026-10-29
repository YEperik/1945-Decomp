#include "ps2_audio_bd_stream.h"

#include <limits.h>
#include <string.h>

int ps2_audio_bd_stream_begin(Ps2AudioBdStreamState *state,
                              uint32_t spu_base_address,
                              uint32_t chunk_size)
{
    if (state == NULL) {
        return 0;
    }
    memset(state, 0, sizeof(*state));
    if (chunk_size == 0u) {
        return 0;
    }
    state->spu_base_address = spu_base_address;
    state->chunk_size = chunk_size;
    state->active = 1u;
    return 1;
}

int ps2_audio_bd_stream_prepare_transfer(Ps2AudioBdStreamState *state,
                                         int32_t read_result,
                                         Ps2AudioBdTransferStep *step)
{
    uint32_t read_bytes;

    if (step != NULL) {
        memset(step, 0, sizeof(*step));
    }
    /* Fail closed on read errors; the inspected IOP routine does not visibly
       guard a negative read result before passing it to VoiceTrans. */
    if (state == NULL || step == NULL || state->active == 0u ||
        state->pending_transfer != 0u || read_result < 0 ||
        (uint32_t)read_result > state->chunk_size) {
        return 0;
    }

    read_bytes = (uint32_t)read_result;
    if (state->bytes_transferred > UINT32_MAX - state->spu_base_address ||
        read_bytes > UINT32_MAX - state->bytes_transferred) {
        return 0;
    }
    if (read_bytes > UINT32_MAX -
                         (state->spu_base_address + state->bytes_transferred)) {
        return 0;
    }

    step->spu_address = state->spu_base_address + state->bytes_transferred;
    step->byte_count = read_bytes;
    step->continue_reading_after_transfer = (uint8_t)(read_bytes == state->chunk_size);
    state->pending_read_bytes = read_bytes;
    state->pending_transfer = 1u;
    state->stop_after_pending_transfer = (uint8_t)(read_bytes != state->chunk_size);
    return 1;
}

int ps2_audio_bd_stream_complete_transfer(Ps2AudioBdStreamState *state,
                                          int32_t voice_transfer_result)
{
    uint32_t transferred;

    if (state == NULL || state->active == 0u || state->pending_transfer == 0u) {
        return 0;
    }
    if (voice_transfer_result != 0) {
        state->active = 0u;
        state->pending_transfer = 0u;
        state->pending_read_bytes = 0u;
        return 0;
    }

    transferred = state->pending_read_bytes;
    if (transferred > UINT32_MAX - state->bytes_transferred) {
        state->active = 0u;
        state->pending_transfer = 0u;
        state->pending_read_bytes = 0u;
        return 0;
    }
    state->bytes_transferred += transferred;
    state->pending_read_bytes = 0u;
    state->pending_transfer = 0u;
    if (state->stop_after_pending_transfer != 0u) {
        state->active = 0u;
    }
    state->stop_after_pending_transfer = 0u;
    return 1;
}

int ps2_audio_bd_stream_should_read(const Ps2AudioBdStreamState *state)
{
    return state != NULL && state->active != 0u && state->pending_transfer == 0u;
}
