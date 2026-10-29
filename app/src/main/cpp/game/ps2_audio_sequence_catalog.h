#ifndef PORT1945_PS2_AUDIO_SEQUENCE_CATALOG_H
#define PORT1945_PS2_AUDIO_SEQUENCE_CATALOG_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct Ps2AudioSequenceResource {
    int32_t sequence_id;
    const char *sequence_stem;
    const char *bank_stem;
    /* Presence only as independent root-level ISO records (not archive lookup). */
    uint8_t has_standalone_sq;
    uint8_t has_standalone_hd;
    uint8_t has_standalone_bd;
} Ps2AudioSequenceResource;

/*
 * Return the selector-table entry observed at 0x001DFCC8 and 0x001DFD20 in
 * the supplied R5900 Listing. The names are logical SND1 stems (no extension).
 * This is metadata only: it does not open/decode files. The standalone flags
 * report only root ISO manifest membership; false does not imply that a
 * resource cannot be present in an as-yet-unresolved aggregate container.
 * IDs 9..12 have root-level .SQ entries but no root-level .HD/.BD records.
 * ID 20 is the literal "0" placeholder; ID 21 has a null sequence pointer.
 */
const Ps2AudioSequenceResource *ps2_audio_sequence_resource_for_id(int32_t sequence_id);

#ifdef __cplusplus
}
#endif

#endif
