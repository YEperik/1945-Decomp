from __future__ import annotations

import csv
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
GAME_DIR = ROOT / "app/src/main/cpp/game"

HARNESS = r'''#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "ps2_audio_resource_loader.h"

static void assert_query(const Ps2AudioResourceQuery *query, uint32_t address,
                         const char *path, int optional) {
    assert(query->command_id == PS2_AUDIO_RPC_QUERY_RESOURCE_SIZE);
    assert(query->ee_request_address == address);
    assert(strcmp(query->path, path) == 0);
    assert(query->optional == (uint8_t)(optional != 0));
}

int main(void) {
    const Ps2AudioLogicalResource *entry;
    Ps2AudioResourcePaths paths;
    Ps2AudioLoadPlan plan;
    const char *optional[PS2_AUDIO_MAX_OPTIONAL_RESOURCES] = {0};
    uint32_t sizes[PS2_AUDIO_MAX_SIZE_QUERIES] = {10u, 20u, 30u, 40u, 50u, 60u, 70u, 80u, 90u};
    uint32_t offsets[PS2_AUDIO_MAX_SIZE_QUERIES] = {0};
    char path[PS2_AUDIO_RESOURCE_PATH_CAPACITY];
    char too_small[8] = "stale";
    uint32_t i;
    size_t path_index;

    assert(ps2_audio_logical_resource_count() == 61u);
    entry = ps2_audio_logical_resource_for_index(0);
    assert(entry != NULL);
    assert(entry->resource_index == 0u);
    assert(entry->table_address == 0x0030C0B0u);
    assert(strcmp(entry->sq_relative_path, "G00\\M_01_VB.SQ") == 0);
    assert(strcmp(entry->hd_relative_path, "G00\\M_01_VB.HD") == 0);
    assert(strcmp(entry->bd_relative_path, "G00\\M_01_VB.BD") == 0);
    assert(entry->duplicate_of_index == PS2_AUDIO_NO_DUPLICATE);

    entry = ps2_audio_logical_resource_for_index(1);
    assert(entry != NULL && entry->duplicate_of_index == 0u);
    entry = ps2_audio_logical_resource_for_index(60);
    assert(entry != NULL && entry->duplicate_of_index == 18u);
    assert(ps2_audio_logical_resource_for_index(-1) == NULL);
    assert(ps2_audio_logical_resource_for_index(61) == NULL);

    assert(ps2_audio_build_iso_path("G00\\M_01_VB.SQ", path, sizeof(path)) == 1);
    assert(strcmp(path, "cdrom0:\\SND\\G00\\M_01_VB.SQ;1") == 0);
    assert(ps2_audio_build_iso_path("G00\\G02.BD", path, sizeof(path)) == 1);
    assert(strcmp(path, "cdrom0:\\SND\\G00\\G02.BD;1") == 0);
    assert(ps2_audio_build_iso_path("ETC\\TAIKO.SQ", path, sizeof(path)) == 1);
    assert(strcmp(path, "cdrom0:\\SND\\ETC\\TAIKO.SQ;1") == 0);
    assert(ps2_audio_build_iso_path("ETC\\TAIKO.BD", path, sizeof(path)) == 1);
    assert(strcmp(path, "cdrom0:\\SND\\ETC\\TAIKO.BD;1") == 0);
    assert(ps2_audio_build_iso_path("ETC\\..\\escape.SQ", path, sizeof(path)) == 0);
    assert(ps2_audio_build_iso_path("G00\\..\\escape.SQ", path, sizeof(path)) == 0);
    assert(path[0] == '\0');
    assert(ps2_audio_build_iso_path("G00\\G02.OLD", path, sizeof(path)) == 0);
    assert(path[0] == '\0');
    assert(ps2_audio_build_iso_path("G00\\G02.SQ", too_small, sizeof(too_small)) == 0);
    assert(too_small[0] == '\0');

    assert(ps2_audio_build_resource_paths(0, &paths) == 1);
    assert(strcmp(paths.sq_path, "cdrom0:\\SND\\G00\\M_01_VB.SQ;1") == 0);
    assert(strcmp(paths.hd_path, "cdrom0:\\SND\\G00\\M_01_VB.HD;1") == 0);
    assert(strcmp(paths.bd_path, "cdrom0:\\SND\\G00\\M_01_VB.BD;1") == 0);

    /* Exhaustively exercise all 61 rows, including the non-Gdd ETC namespace. */
    for (path_index = 0u; path_index < ps2_audio_logical_resource_count(); ++path_index) {
        const Ps2AudioLogicalResource *resource =
            ps2_audio_logical_resource_for_index((int32_t)path_index);
        assert(resource != NULL);
        assert(ps2_audio_build_resource_paths((int32_t)path_index, &paths) == 1);
        assert(strncmp(paths.sq_path, "cdrom0:\\SND\\", 12u) == 0);
        assert(strstr(paths.sq_path, resource->sq_relative_path) != NULL);
        assert(strstr(paths.hd_path, resource->hd_relative_path) != NULL);
        assert(strstr(paths.bd_path, resource->bd_relative_path) != NULL);
        assert(strstr(paths.sq_path, ";1") != NULL);
        assert(strstr(paths.hd_path, ";1") != NULL);
        assert(strstr(paths.bd_path, ";1") != NULL);
    }
    assert(ps2_audio_build_resource_paths(54, &paths) == 1);
    assert(strcmp(paths.sq_path, "cdrom0:\\SND\\ETC\\TAIKO.SQ;1") == 0);
    assert(ps2_audio_build_resource_paths(61, &paths) == 0);
    assert(paths.sq_path[0] == '\0' && paths.hd_path[0] == '\0' && paths.bd_path[0] == '\0');

    /* Group switch path: shared SE.HD, this SQ/HD, no optional banks, then this BD. */
    assert(ps2_audio_build_group_switch_plan(0, NULL, &plan) == 1);
    assert(plan.resource_index == 0u);
    assert(plan.allocates_resource_pool == 0u);
    assert(plan.size_query_count == 3u);
    assert_query(&plan.size_queries[0], 0x003BB180u, "cdrom0:\\SND1\\SE.HD;1", 0);
    assert_query(&plan.size_queries[1], 0x0030C3C0u, "cdrom0:\\SND\\G00\\M_01_VB.SQ;1", 0);
    assert_query(&plan.size_queries[2], 0x003BB100u, "cdrom0:\\SND\\G00\\M_01_VB.HD;1", 0);
    assert(plan.sample_transfer_count == 1u);
    assert(plan.sample_transfers[0].transfer_command_id == PS2_AUDIO_RPC_TRANSFER_SAMPLE_BANK);
    assert(plan.sample_transfers[0].ee_request_address == 0x003BB080u);
    assert(plan.sample_transfers[0].is_common_bank == 0u);
    assert(strcmp(plan.sample_transfers[0].path, "cdrom0:\\SND\\G00\\M_01_VB.BD;1") == 0);
    assert(plan.sample_transfers[0].setup_command_ids[0] == PS2_AUDIO_RPC_SAMPLE_SETUP_GROUP);
    assert(plan.sample_transfers[0].setup_values[1] == 0x2010u);
    assert(plan.sample_transfers[0].setup_values[2] == 0x80u);

    /* Initial setup adds the common SE.BD transfer before the group's BD. */
    assert(ps2_audio_build_initial_load_plan(2, NULL, &plan) == 1);
    assert(plan.allocates_resource_pool == 1u);
    assert(plan.sample_transfer_count == 2u);
    assert(plan.sample_transfers[0].is_common_bank == 1u);
    assert(strcmp(plan.sample_transfers[0].path, "cdrom0:\\SND1\\SE.BD;1") == 0);
    assert(plan.sample_transfers[0].setup_command_ids[0] == PS2_AUDIO_RPC_SAMPLE_SETUP_INITIAL);
    assert(plan.sample_transfers[0].setup_values[1] == 0x1840u);
    assert(plan.sample_transfers[0].setup_values[2] == 0x100u);
    assert(plan.sample_transfers[1].is_common_bank == 0u);
    assert(strcmp(plan.sample_transfers[1].path, "cdrom0:\\SND\\G20\\G26.BD;1") == 0);

    /* Optional paths keep their original request slots even when earlier slots are empty. */
    optional[2] = "cdrom0:\\SND1\\BOSS2.SQ;1";
    optional[5] = "cdrom0:\\SND1\\CLEAR2.SQ;1";
    assert(ps2_audio_build_group_switch_plan(3, optional, &plan) == 1);
    assert(plan.size_query_count == 5u);
    assert_query(&plan.size_queries[3], 0x003BB240u, "cdrom0:\\SND1\\BOSS2.SQ;1", 1);
    assert_query(&plan.size_queries[4], 0x003BB300u, "cdrom0:\\SND1\\CLEAR2.SQ;1", 1);
    optional[5] = "cdrom0:\\SND1\\..\\bad.SQ;1";
    assert(ps2_audio_build_group_switch_plan(3, optional, &plan) == 0);
    optional[5] = NULL;

    assert(ps2_audio_calculate_pool_layout(0x10000000u, sizes, offsets) == 1);
    assert(offsets[0] == 0x10000000u);
    assert(offsets[1] == 0x1000000Au);
    assert(offsets[2] == 0x1000001Eu);
    assert(offsets[3] == 0x1000003Cu);
    assert(offsets[8] == 0x10000168u);
    for (i = 0u; i < PS2_AUDIO_MAX_SIZE_QUERIES; ++i) {
        sizes[i] = 0u;
    }
    sizes[8] = PS2_AUDIO_RESOURCE_POOL_SIZE;
    assert(ps2_audio_calculate_pool_layout(0x10000000u, sizes, offsets) == 1);
    assert(offsets[8] == 0x10000000u); /* Exact 0x8000-byte fit is accepted. */

    for (i = 0u; i < PS2_AUDIO_MAX_SIZE_QUERIES; ++i) {
        offsets[i] = 0xA5A5A5A5u;
    }
    sizes[8] = PS2_AUDIO_RESOURCE_POOL_SIZE + 1u;
    assert(ps2_audio_calculate_pool_layout(0x10000000u, sizes, offsets) == 0);
    for (i = 0u; i < PS2_AUDIO_MAX_SIZE_QUERIES; ++i) {
        assert(offsets[i] == 0xA5A5A5A5u); /* Failure must not partially overwrite outputs. */
    }
    sizes[8] = 1u;
    assert(ps2_audio_calculate_pool_layout(UINT32_MAX, sizes, offsets) == 0);
    for (i = 0u; i < PS2_AUDIO_MAX_SIZE_QUERIES; ++i) {
        assert(offsets[i] == 0xA5A5A5A5u);
    }

    /* Print rows so Python can compare the compiled C catalog to the evidence CSV. */
    for (i = 0u; i < ps2_audio_logical_resource_count(); ++i) {
        entry = ps2_audio_logical_resource_for_index((int32_t)i);
        assert(entry != NULL);
        printf("%u,%08x,%s,%s,%s,%u\n", (unsigned int)entry->resource_index,
               (unsigned int)entry->table_address, entry->sq_relative_path,
               entry->hd_relative_path, entry->bd_relative_path,
               (unsigned int)entry->duplicate_of_index);
    }
    return 0;
}
'''


def test_ps2_audio_resource_loader_reference_model_matches_ghidra_catalog(tmp_path: pathlib.Path) -> None:
    source = tmp_path / "ps2_audio_resource_loader_harness.c"
    executable = tmp_path / "ps2_audio_resource_loader_harness"
    source.write_text(HARNESS, encoding="utf-8")
    subprocess.run(
        ["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wconversion",
         "-Wsign-conversion", "-pedantic", "-I", str(GAME_DIR), str(source),
         str(GAME_DIR / "ps2_audio_resource_loader.c"), "-o", str(executable)],
        check=True, capture_output=True, text=True,
    )
    completed = subprocess.run([str(executable)], check=True, capture_output=True, text=True)
    actual = [line.split(",") for line in completed.stdout.splitlines()]

    with (ROOT / "evidence/ghidra_audio_logical_resource_catalog.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        expected_rows = list(csv.DictReader(stream))

    assert len(actual) == len(expected_rows) == 61
    for actual_row, expected in zip(actual, expected_rows, strict=True):
        index, address, sq, hd, bd, duplicate = actual_row
        assert int(index) == int(expected["resource_index"])
        assert int(address, 16) == int(expected["table_address"], 16)
        assert sq == expected["sq_path_key"]
        assert hd == expected["hd_path_key"]
        assert bd == expected["bd_path_key"]
        expected_duplicate = 65535 if not expected["duplicate_of_index"] else int(expected["duplicate_of_index"])
        assert int(duplicate) == expected_duplicate
