from __future__ import annotations

import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
GAME_DIR = ROOT / "app/src/main/cpp/game"

HARNESS = r'''#include <assert.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include "ps2_audio_cdrom_path.h"
#include "ps2_audio_snd2_sequence_catalog.h"

int main(void) {
    char output[256];
    assert(ps2_audio_make_cdrom0_path("snd2/sq_010.sq", output, sizeof(output)) == 1);
    assert(strcmp(output, "cdrom0:\\SND2\\SQ_010.SQ;1") == 0);

    /* Cross-check every catalog entry against the output of the path helper. */
    for (int32_t i = 0; i < PS2_SND2_SEQUENCE_SLOT_COUNT; ++i) {
        const Ps2Snd2SequenceSlot *slot = ps2_audio_snd2_sequence_slot_for_index(i);
        char normalized[128];
        char expected[160];
        size_t path_index;
        assert(slot != NULL);
        for (path_index = 0u; path_index < strlen(slot->resolved_iso_path); ++path_index) {
            char value = slot->resolved_iso_path[path_index];
            normalized[path_index] = value == '/' ? '\\' : value;
        }
        normalized[path_index] = '\0';
        assert(snprintf(expected, sizeof(expected), "cdrom0:\\%s", normalized) > 0);
        assert(ps2_audio_make_cdrom0_path(slot->logical_path, output, sizeof(output)) == 1);
        assert(strcmp(output, expected) == 0);
    }

    assert(ps2_audio_make_cdrom0_path("SND2/SQ_001.SQ;7", output, sizeof(output)) == 1);
    assert(strcmp(output, "cdrom0:\\SND2\\SQ_001.SQ;1") == 0);

    assert(ps2_audio_make_cdrom0_path("cdrom0:\\SND2\\SQ_001.SQ;1", output,
                                      sizeof(output)) == 1);
    assert(strcmp(output, "cdrom0:\\SND2\\SQ_001.SQ;1") == 0);

    assert(ps2_audio_make_cdrom0_path("host0:snd2/sq_002.sq;1", output,
                                      sizeof(output)) == 1);
    assert(strcmp(output, "cdrom0:\\SND2\\SQ_002.SQ;1") == 0);

    assert(ps2_audio_make_cdrom0_path("/snd2/sq_003.sq", output, sizeof(output)) == 1);
    assert(strcmp(output, "cdrom0:\\SND2\\SQ_003.SQ;1") == 0);

    memset(output, 'X', sizeof(output));
    assert(ps2_audio_make_cdrom0_path("snd2/sq_001.sq", output, 8u) == 0);
    assert(output[0] == '\0');
    assert(ps2_audio_make_cdrom0_path(NULL, output, sizeof(output)) == 0);
    assert(output[0] == '\0');
    assert(ps2_audio_make_cdrom0_path("snd2/sq_001.sq", NULL, sizeof(output)) == 0);
    assert(ps2_audio_make_cdrom0_path("snd2/sq_001.sq", output, 0u) == 0);
    return 0;
}
'''


def test_ps2_cdrom_path_normalization_matches_observed_contract(tmp_path: pathlib.Path) -> None:
    source = tmp_path / "cdrom_path_harness.c"
    executable = tmp_path / "cdrom_path_harness"
    source.write_text(HARNESS, encoding="utf-8")
    subprocess.run(
        ["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wconversion",
         "-Wsign-conversion", "-pedantic", "-I", str(GAME_DIR), str(source),
         str(GAME_DIR / "ps2_audio_cdrom_path.c"),
         str(GAME_DIR / "ps2_audio_snd2_sequence_catalog.c"), "-o", str(executable)],
        check=True, capture_output=True, text=True,
    )
    subprocess.run([str(executable)], check=True, capture_output=True, text=True)
