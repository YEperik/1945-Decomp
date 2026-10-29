from __future__ import annotations

import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
GAME_DIR = ROOT / "app/src/main/cpp/game"

HARNESS = r'''#include <assert.h>
#include <stddef.h>
#include <string.h>
#include "ps2_audio_sequence_catalog.h"

static void assert_resource(int32_t id, const char *sequence, const char *bank,
                            uint8_t has_sq, uint8_t has_hd, uint8_t has_bd) {
    const Ps2AudioSequenceResource *entry = ps2_audio_sequence_resource_for_id(id);
    assert(entry != NULL);
    assert(entry->sequence_id == id);
    assert(strcmp(entry->sequence_stem, sequence) == 0);
    assert(strcmp(entry->bank_stem, bank) == 0);
    assert(entry->has_standalone_sq == has_sq);
    assert(entry->has_standalone_hd == has_hd);
    assert(entry->has_standalone_bd == has_bd);
}

int main(void) {
    assert_resource(0, "end_r", "end", 1u, 1u, 1u);
    assert_resource(1, "bgm5", "bgm", 1u, 1u, 1u);
    assert_resource(2, "bgm6", "bgm", 1u, 1u, 1u);
    assert_resource(3, "bgm7", "bgm", 1u, 1u, 1u);
    assert_resource(4, "bgm8", "bgm", 1u, 1u, 1u);
    assert_resource(5, "bgma", "bgm", 1u, 1u, 1u);
    assert_resource(6, "bgmb", "bgm", 1u, 1u, 1u);
    assert_resource(7, "bgmc", "bgm", 1u, 1u, 1u);
    assert_resource(8, "bgmd", "bgm", 1u, 1u, 1u);
    /* Root ISO records include the boss SQs, but not their named HD/BD banks. */
    assert_resource(9, "boss2", "boss2", 1u, 0u, 0u);
    assert_resource(10, "boss3", "boss3", 1u, 0u, 0u);
    assert_resource(11, "boss4", "boss4", 1u, 0u, 0u);
    assert_resource(12, "clear2", "clear2", 1u, 0u, 0u);
    assert_resource(13, "end_r", "end", 1u, 1u, 1u);
    assert_resource(14, "end_r2", "end", 1u, 1u, 1u);
    assert_resource(15, "menu", "menu", 1u, 1u, 1u);
    assert_resource(16, "name", "name", 1u, 1u, 1u);
    assert_resource(17, "sel_2", "sel_2", 1u, 1u, 1u);
    assert_resource(18, "sel_2", "sel_2", 1u, 1u, 1u);
    assert_resource(19, "sel_2", "sel_2", 1u, 1u, 1u);
    assert_resource(20, "0", "0", 0u, 0u, 0u);
    assert(ps2_audio_sequence_resource_for_id(21) == NULL);
    assert(ps2_audio_sequence_resource_for_id(-1) == NULL);
    assert(ps2_audio_sequence_resource_for_id(22) == NULL);
    return 0;
}
'''


def test_ps2_audio_sequence_catalog_exact_selector_order(tmp_path: pathlib.Path) -> None:
    source = tmp_path / "ps2_audio_sequence_catalog_harness.c"
    executable = tmp_path / "ps2_audio_sequence_catalog_harness"
    source.write_text(HARNESS, encoding="utf-8")
    subprocess.run(
        ["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wconversion",
         "-Wsign-conversion", "-pedantic", "-I", str(GAME_DIR), str(source),
         str(GAME_DIR / "ps2_audio_sequence_catalog.c"), "-o", str(executable)],
        check=True, capture_output=True, text=True,
    )
    subprocess.run([str(executable)], check=True, capture_output=True, text=True)
