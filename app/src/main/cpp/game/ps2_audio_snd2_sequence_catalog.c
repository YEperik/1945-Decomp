#include "ps2_audio_snd2_sequence_catalog.h"

static const Ps2Snd2SequenceSlot k_snd2_sequences[PS2_SND2_SEQUENCE_SLOT_COUNT] = {
    {0, 1, 0x0027A9A8u, 0x0032A658u, PS2_AUDIO_SND2_EMPTY_SLOT, "sq_001.sq", "snd2/sq_001.sq", "SND2/SQ_001.SQ;1"},
    {1, 2, 0x0027A9ACu, 0x0032A668u, PS2_AUDIO_SND2_EMPTY_SLOT, "sq_002.sq", "snd2/sq_002.sq", "SND2/SQ_002.SQ;1"},
    {2, 3, 0x0027A9B0u, 0x0032A678u, PS2_AUDIO_SND2_EMPTY_SLOT, "sq_003.sq", "snd2/sq_003.sq", "SND2/SQ_003.SQ;1"},
    {3, 4, 0x0027A9B4u, 0x0032A688u, PS2_AUDIO_SND2_EMPTY_SLOT, "sq_004.sq", "snd2/sq_004.sq", "SND2/SQ_004.SQ;1"},
    {4, 5, 0x0027A9B8u, 0x0032A698u, PS2_AUDIO_SND2_EMPTY_SLOT, "sq_005.sq", "snd2/sq_005.sq", "SND2/SQ_005.SQ;1"},
    {5, 6, 0x0027A9BCu, 0x0032A6A8u, PS2_AUDIO_SND2_EMPTY_SLOT, "sq_006.sq", "snd2/sq_006.sq", "SND2/SQ_006.SQ;1"},
    {6, 7, 0x0027A9C0u, 0x0032A6B8u, PS2_AUDIO_SND2_EMPTY_SLOT, "sq_007.sq", "snd2/sq_007.sq", "SND2/SQ_007.SQ;1"},
    {7, 8, 0x0027A9C4u, 0x0032A6C8u, PS2_AUDIO_SND2_EMPTY_SLOT, "sq_008.sq", "snd2/sq_008.sq", "SND2/SQ_008.SQ;1"},
    {8, 9, 0x0027A9C8u, 0x0032A6D8u, PS2_AUDIO_SND2_EMPTY_SLOT, "sq_009.sq", "snd2/sq_009.sq", "SND2/SQ_009.SQ;1"},
    {9, 10, 0x0027A9CCu, 0x0032A6E8u, PS2_AUDIO_SND2_EMPTY_SLOT, "sq_010.sq", "snd2/sq_010.sq", "SND2/SQ_010.SQ;1"},
    {10, 10, 0x0027A9D0u, 0x0032A6E8u, 9, "sq_010.sq", "snd2/sq_010.sq", "SND2/SQ_010.SQ;1"},
    {11, 11, 0x0027A9D4u, 0x0032A6F8u, PS2_AUDIO_SND2_EMPTY_SLOT, "sq_011.sq", "snd2/sq_011.sq", "SND2/SQ_011.SQ;1"},
    {12, 12, 0x0027A9D8u, 0x0032A708u, PS2_AUDIO_SND2_EMPTY_SLOT, "sq_012.sq", "snd2/sq_012.sq", "SND2/SQ_012.SQ;1"},
    {13, 13, 0x0027A9DCu, 0x0032A718u, PS2_AUDIO_SND2_EMPTY_SLOT, "sq_013.sq", "snd2/sq_013.sq", "SND2/SQ_013.SQ;1"},
    {14, 14, 0x0027A9E0u, 0x0032A728u, PS2_AUDIO_SND2_EMPTY_SLOT, "sq_014.sq", "snd2/sq_014.sq", "SND2/SQ_014.SQ;1"},
    {15, 15, 0x0027A9E4u, 0x0032A738u, PS2_AUDIO_SND2_EMPTY_SLOT, "sq_015.sq", "snd2/sq_015.sq", "SND2/SQ_015.SQ;1"},
    {16, 16, 0x0027A9E8u, 0x0032A748u, PS2_AUDIO_SND2_EMPTY_SLOT, "sq_016.sq", "snd2/sq_016.sq", "SND2/SQ_016.SQ;1"},
    {17, 17, 0x0027A9ECu, 0x0032A758u, PS2_AUDIO_SND2_EMPTY_SLOT, "sq_017.sq", "snd2/sq_017.sq", "SND2/SQ_017.SQ;1"},
};

size_t ps2_audio_snd2_sequence_slot_count(void)
{
    return sizeof(k_snd2_sequences) / sizeof(k_snd2_sequences[0]);
}

const Ps2Snd2SequenceSlot *ps2_audio_snd2_sequence_slot_for_index(int32_t index)
{
    if (index < 0 || (uint32_t)index >= (uint32_t)PS2_SND2_SEQUENCE_SLOT_COUNT) {
        return NULL;
    }
    return &k_snd2_sequences[(size_t)index];
}

const char *ps2_audio_snd2_optional_path_for_index(int32_t index)
{
    const Ps2Snd2SequenceSlot *slot;

    if (index < 0 || index >= PS2_AUDIO_OPTIONAL_PATH_CAPACITY) {
        return NULL;
    }
    if (index >= PS2_SND2_SEQUENCE_SLOT_COUNT) {
        return NULL;
    }
    slot = ps2_audio_snd2_sequence_slot_for_index(index);
    return slot == NULL ? NULL : slot->logical_path;
}
