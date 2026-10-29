#ifndef PORT1945_PS2_AUDIO_SND2_SEQUENCE_CATALOG_H
#define PORT1945_PS2_AUDIO_SND2_SEQUENCE_CATALOG_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define PS2_SND2_SEQUENCE_SLOT_COUNT 18
#define PS2_AUDIO_OPTIONAL_PATH_CAPACITY 32
#define PS2_AUDIO_SND2_EMPTY_SLOT (-1)

typedef struct Ps2Snd2SequenceSlot {
    int32_t loader_slot_index;
    int32_t sequence_number;
    uint32_t pointer_entry_address;
    uint32_t string_address;
    int32_t duplicate_of_slot;
    const char *logical_filename;
    const char *logical_path;
    const char *resolved_iso_path;
} Ps2Snd2SequenceSlot;

/*
 * Metadata-only reconstruction of the 18-entry table at 0x0027A9A8.
 * It does not perform CDVD I/O, SIF RPC, sequence parsing, or playback.
 */
size_t ps2_audio_snd2_sequence_slot_count(void);
const Ps2Snd2SequenceSlot *ps2_audio_snd2_sequence_slot_for_index(int32_t index);

/*
 * Return the optional path initialized for a 0..31 loader slot, or NULL when
 * the observed SND2 initializer leaves that slot empty or the index is invalid.
 */
const char *ps2_audio_snd2_optional_path_for_index(int32_t index);

#ifdef __cplusplus
}
#endif

#endif
