from __future__ import annotations

import csv
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))
from parse_ghidra_audio_tables import ListingError, parse_resource_groups

ROOT = pathlib.Path(__file__).resolve().parents[1]


def listing_line(address: int, label: str, path: str) -> str:
    encoded = path.replace("\\", "\\\\")
    return (
        f'.data:{address:08x}  00000000        addr        '
        f'.rodata:s_{label}_{address:08x} ;= "{encoded}"'
    )


def test_parse_resource_triplet_and_duplicate_metadata() -> None:
    lines = [
        listing_line(0x0030C0B0, "G00_G02_SQ", r"G00\G02.SQ"),
        listing_line(0x0030C0B4, "G00_G02_HD", r"G00\G02.HD"),
        listing_line(0x0030C0B8, "G00_G02_BD", r"G00\G02.BD"),
        listing_line(0x0030C0BC, "G00_G02_SQ", r"G00\G02.SQ"),
        listing_line(0x0030C0C0, "G00_G02_HD", r"G00\G02.HD"),
        listing_line(0x0030C0C4, "G00_G02_BD", r"G00\G02.BD"),
    ]
    rows = parse_resource_groups("\n".join(lines))
    assert len(rows) == 2
    assert rows[0]["resource_index"] == 0
    assert rows[0]["sq_path_key"] == r"G00\G02.SQ"
    assert rows[0]["duplicate_of_index"] == ""
    assert rows[1]["duplicate_of_index"] == 0


def test_parse_resource_table_rejects_bad_triplet() -> None:
    lines = [
        listing_line(0x0030C0B0, "G00_G02_SQ", r"G00\G02.SQ"),
        listing_line(0x0030C0B4, "G00_G02_HD", r"G00\G02.HD"),
        listing_line(0x0030C0B8, "G00_G02_OTHER", r"G00\G02.OLD"),
    ]
    with pytest.raises(ListingError):
        parse_resource_groups("\n".join(lines))


def test_checked_in_catalog_evidence_is_complete_and_flags_missing_banks() -> None:
    sequence_path = ROOT / "evidence/ghidra_audio_sequence_catalog.csv"
    resource_path = ROOT / "evidence/ghidra_audio_logical_resource_catalog.csv"
    root_paths = ROOT / "evidence/ghidra_audio_root_path_catalog.csv"
    with sequence_path.open(encoding="utf-8", newline="") as stream:
        sequences = list(csv.DictReader(stream))
    with resource_path.open(encoding="utf-8", newline="") as stream:
        resources = list(csv.DictReader(stream))
    with root_paths.open(encoding="utf-8", newline="") as stream:
        root_audio = list(csv.DictReader(stream))

    assert len(sequences) == 22
    assert len(resources) == 61
    assert len(root_audio) == 30
    assert [r["sequence_id"] for r in sequences if r["sequence_and_bank_paths_physically_present"] == "False"] == ["9", "10", "11", "12", "20", "21"]
    assert sum(r["manifest_status"] == "present" for r in root_audio) == 29
    assert [r["resource_index"] for r in resources if r["duplicate_of_index"]] == ["1", "60"]


def test_active_stage_sequence_targets_have_complete_standalone_resources() -> None:
    sequence_path = ROOT / "evidence/ghidra_audio_sequence_catalog.csv"
    with sequence_path.open(encoding="utf-8", newline="") as stream:
        sequences = {int(r["sequence_id"]): r for r in csv.DictReader(stream)}

    # Derived only from the current portable transcription of FUN_00101940
    # plus the BGM_STAGE fallback in FUN_00101AC8. This is not a claim that
    # every stage or boss event has been modeled.
    active_stage_ids = set(range(1, 9)) | {14, 15, 16, 17}
    assert active_stage_ids.issubset(sequences)
    for sequence_id in active_stage_ids:
        row = sequences[sequence_id]
        assert row["sq_manifest_status"] == "present", sequence_id
        assert row["hd_manifest_status"] == "present", sequence_id
        assert row["bd_manifest_status"] == "present", sequence_id


def test_boss_and_clear_sequences_have_sq_but_unmatched_standalone_banks() -> None:
    sequence_path = ROOT / "evidence/ghidra_audio_sequence_catalog.csv"
    with sequence_path.open(encoding="utf-8", newline="") as stream:
        sequences = {int(r["sequence_id"]): r for r in csv.DictReader(stream)}
    for sequence_id in (9, 10, 11, 12):
        row = sequences[sequence_id]
        assert row["sq_manifest_status"] == "present"
        assert row["hd_manifest_status"] == "missing_from_iso_manifest"
        assert row["bd_manifest_status"] == "missing_from_iso_manifest"


def test_bgm_boss_callback_table_targets_match_listing_evidence() -> None:
    import json

    validation_path = ROOT / "evidence/ghidra_audio_catalog_validation.json"
    report = json.loads(validation_path.read_text(encoding="utf-8"))
    assert [int(row["target_address"], 16) for row in report["bgm_boss_callback_table"]] == [
        0x00192490, 0x001924C0, 0x001924F0, 0x00192520
    ]
