from __future__ import annotations

import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
GAME_DIR = ROOT / "app/src/main/cpp/game"

HARNESS = r'''#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include "ps2_audio_snd2_sequence_catalog.h"

int main(void) {
    static const char *const expected_names[18] = {
        "sq_001.sq", "sq_002.sq", "sq_003.sq", "sq_004.sq", "sq_005.sq",
        "sq_006.sq", "sq_007.sq", "sq_008.sq", "sq_009.sq", "sq_010.sq",
        "sq_010.sq", "sq_011.sq", "sq_012.sq", "sq_013.sq", "sq_014.sq",
        "sq_015.sq", "sq_016.sq", "sq_017.sq",
    };
    assert(ps2_audio_snd2_sequence_slot_count() == 18u);
    for (int32_t i = 0; i < 18; ++i) {
        const Ps2Snd2SequenceSlot *slot = ps2_audio_snd2_sequence_slot_for_index(i);
        assert(slot != NULL);
        assert(slot->loader_slot_index == i);
        assert(slot->pointer_entry_address == 0x0027A9A8u + (uint32_t)i * 4u);
        assert(strcmp(slot->logical_filename, expected_names[i]) == 0);
        assert(ps2_audio_snd2_optional_path_for_index(i) != NULL);
        assert(strcmp(slot->resolved_iso_path, "") != 0);
    }
    const Ps2Snd2SequenceSlot *slot9 = ps2_audio_snd2_sequence_slot_for_index(9);
    const Ps2Snd2SequenceSlot *slot10 = ps2_audio_snd2_sequence_slot_for_index(10);
    assert(slot9 != NULL && slot10 != NULL);
    assert(strcmp(slot9->logical_filename, "sq_010.sq") == 0);
    assert(strcmp(slot10->logical_filename, "sq_010.sq") == 0);
    assert(slot9->string_address == slot10->string_address);
    assert(slot10->duplicate_of_slot == 9);
    assert(slot9->duplicate_of_slot == PS2_AUDIO_SND2_EMPTY_SLOT);
    assert(strcmp(ps2_audio_snd2_optional_path_for_index(0), "snd2/sq_001.sq") == 0);
    assert(strcmp(ps2_audio_snd2_optional_path_for_index(17), "snd2/sq_017.sq") == 0);
    for (int32_t i = 18; i < PS2_AUDIO_OPTIONAL_PATH_CAPACITY; ++i) {
        assert(ps2_audio_snd2_sequence_slot_for_index(i) == NULL);
        assert(ps2_audio_snd2_optional_path_for_index(i) == NULL);
    }
    assert(ps2_audio_snd2_sequence_slot_for_index(-1) == NULL);
    assert(ps2_audio_snd2_sequence_slot_for_index(18) == NULL);
    assert(ps2_audio_snd2_optional_path_for_index(-1) == NULL);
    assert(ps2_audio_snd2_optional_path_for_index(32) == NULL);
    return 0;
}
'''


def test_ps2_audio_snd2_catalog_and_duplicate_slot(tmp_path: pathlib.Path) -> None:
    source = tmp_path / "snd2_catalog_harness.c"
    executable = tmp_path / "snd2_catalog_harness"
    source.write_text(HARNESS, encoding="utf-8")
    subprocess.run(
        ["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wconversion",
         "-Wsign-conversion", "-pedantic", "-I", str(GAME_DIR), str(source),
         str(GAME_DIR / "ps2_audio_snd2_sequence_catalog.c"), "-o", str(executable)],
        check=True, capture_output=True, text=True,
    )
    subprocess.run([str(executable)], check=True, capture_output=True, text=True)
