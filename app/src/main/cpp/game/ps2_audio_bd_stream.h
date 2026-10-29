#ifndef PORT1945_PS2_AUDIO_BD_STREAM_H
#define PORT1945_PS2_AUDIO_BD_STREAM_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct Ps2AudioBdStreamState {
    uint32_t spu_base_address;
    uint32_t chunk_size;
    uint32_t bytes_transferred;
    uint32_t pending_read_bytes;
    uint8_t pending_transfer;
    uint8_t active;
    uint8_t stop_after_pending_transfer;
} Ps2AudioBdStreamState;

typedef struct Ps2AudioBdTransferStep {
    uint32_t spu_address;
    uint32_t byte_count;
    uint8_t continue_reading_after_transfer;
} Ps2AudioBdTransferStep;

/*
 * Reference model for EZMIDI.IRX MidiTransBdPacket (module offset 0x0ED4).
 * Reads are supplied by the caller; this module performs no file or SPU I/O.
 */
int ps2_audio_bd_stream_begin(Ps2AudioBdStreamState *state,
                              uint32_t spu_base_address,
                              uint32_t chunk_size);
int ps2_audio_bd_stream_prepare_transfer(Ps2AudioBdStreamState *state,
                                         int32_t read_result,
                                         Ps2AudioBdTransferStep *step);
int ps2_audio_bd_stream_complete_transfer(Ps2AudioBdStreamState *state,
                                          int32_t voice_transfer_result);
int ps2_audio_bd_stream_should_read(const Ps2AudioBdStreamState *state);

#ifdef __cplusplus
}
#endif

#endif
