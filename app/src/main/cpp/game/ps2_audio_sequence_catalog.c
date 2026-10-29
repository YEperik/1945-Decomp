#include "ps2_audio_sequence_catalog.h"

#include <stddef.h>

/*
 * Selector order follows 0x001DFCC8 / 0x001DFD20. IDs 1..8 are cross-correlated
 * against the explicit root path table at 0x001DFE08..0x001DFE24 and the eight
 * BGM5..BGMD SQ records in ISO LBA order. Standalone presence flags come from
 * evidence/ghidra_audio_sequence_catalog.csv; they do not describe pack lookup.
 */
static const Ps2AudioSequenceResource k_sequence_resources[] = {
    {0,  "end_r", "end",    1u, 1u, 1u},
    {1,  "bgm5",  "bgm",    1u, 1u, 1u},
    {2,  "bgm6",  "bgm",    1u, 1u, 1u},
    {3,  "bgm7",  "bgm",    1u, 1u, 1u},
    {4,  "bgm8",  "bgm",    1u, 1u, 1u},
    {5,  "bgma",  "bgm",    1u, 1u, 1u},
    {6,  "bgmb",  "bgm",    1u, 1u, 1u},
    {7,  "bgmc",  "bgm",    1u, 1u, 1u},
    {8,  "bgmd",  "bgm",    1u, 1u, 1u},
    {9,  "boss2", "boss2",  1u, 0u, 0u},
    {10, "boss3", "boss3",  1u, 0u, 0u},
    {11, "boss4", "boss4",  1u, 0u, 0u},
    {12, "clear2", "clear2", 1u, 0u, 0u},
    {13, "end_r", "end",   1u, 1u, 1u},
    {14, "end_r2", "end",  1u, 1u, 1u},
    {15, "menu", "menu",   1u, 1u, 1u},
    {16, "name", "name",   1u, 1u, 1u},
    {17, "sel_2", "sel_2", 1u, 1u, 1u},
    {18, "sel_2", "sel_2", 1u, 1u, 1u},
    {19, "sel_2", "sel_2", 1u, 1u, 1u},
    {20, "0", "0",         0u, 0u, 0u},
    {21, NULL, "0",         0u, 0u, 0u},
};

const Ps2AudioSequenceResource *ps2_audio_sequence_resource_for_id(int32_t sequence_id)
{
    size_t index;

    if (sequence_id < 0 || (uint32_t)sequence_id >=
        (uint32_t)(sizeof(k_sequence_resources) / sizeof(k_sequence_resources[0]))) {
        return NULL;
    }
    index = (size_t)sequence_id;
    if (k_sequence_resources[index].sequence_stem == NULL) {
        return NULL;
    }
    return &k_sequence_resources[index];
}
