from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_checked_in_embedded_block_probe_is_hash_verified_and_metadata_only() -> None:
    report = json.loads((ROOT / "evidence/ps2_audio_embedded_block_probe.json").read_text(encoding="utf-8"))
    assert report["input_count"] == 6
    by_name = {row["input_name"]: row for row in report["reports"]}
    assert set(by_name) == {"SNDCOM", "UBF", "UBF_P", "SEQDAT_E", "SEQDAT_J", "SEQDAT_K"}
    expected_files = {
        "SNDCOM": (381542, "9fbaa078c94c1715234d0fae142a739a592bcd194066fbd9ccca2856892e2c29"),
        "UBF": (47472640, "18bb4d08297be709615eb31781abe27569b0550fa8a01a664de524f95be722b4"),
        "UBF_P": (149504, "a866c0d5af295684f74cce37dfef789e40e62c00c78ccb060544606c1e010106"),
        "SEQDAT_E": (1152540, "2ed786bafc09afb210982723898f0613e53e9ac82875d4d561e8de0b6db94a3f"),
        "SEQDAT_J": (1152576, "d71dd150c24617072ea0954d6c4a98b6da931a76798ab1c1da7c258c80fc5066"),
        "SEQDAT_K": (1152540, "8cf79dd402498ae045a8c59c499098581dc879f46d6136c7cefc74412c913bea"),
    }
    for name, (size_bytes, digest) in expected_files.items():
        row = by_name[name]
        assert row["size_bytes"] == size_bytes
        assert row["sha256"] == digest
        assert row["expected_sha256"] == digest
        assert row["expected_sha256_matches"] is True

    sndcom = by_name["SNDCOM"]
    directory = sndcom["compact_directory_table_candidate"]
    assert directory["detected"] is True
    assert directory["entry_count_candidate"] == 7
    assert [row["target_offset_hex"] for row in directory["entries"]] == [
        "0x3C", "0x3D8", "0x31F8", "0x1C7A8", "0x239C8", "0x5A7D8", "0x5C012"
    ]
    assert [row["tag_ascii_if_byte"] for row in directory["entries"]] == ["1", "8", "9", ":", ";", "0", "2"]
    assert [row["recognized_marker_at_target"] for row in directory["entries"]] == [
        "pQES", "pBAV", None, "pBAV", None, "pQES", "pQES"
    ]
    assert [row["candidate_end_offset_hex"] for row in sndcom["pBAV_candidate_headers"]] == ["0x1C7A8", "0x5A7D8"]
    assert all(row["candidate_size_in_bounds"] for row in sndcom["pBAV_candidate_headers"])
    assert all(row["gap_to_next_recognized_marker_bytes"] == 0 for row in sndcom["pBAV_candidate_headers"])

    ubf = by_name["UBF"]
    assert ubf["marker_counts_and_offsets"]["pQES"]["count_observed"] == 17
    assert ubf["marker_counts_and_offsets"]["pBAV"]["count_observed"] == 1
    assert ubf["marker_counts_and_offsets"]["BGMAP"]["count_observed"] == 41
    # These adjacent-format labels point toward map/graphics metadata; they are
    # not sufficient to classify UBF or its BGMAP hit as an audio object.
    context = ubf["context_string_hits"]
    assert context["RECTDT  SEQUENCE"]["count_observed"] == 20
    assert context["PALETTE BGMAPTBL"]["count_observed"] == 5
    assert context["CHECKSUMSEQUENCE"]["count_observed"] == 5
    assert context["BGMAP   OBJDT"]["count_observed"] == 1
    ubf_block = ubf["pBAV_candidate_headers"][0]
    assert ubf_block["candidate_end_offset_hex"] == "0x83BB0"
    assert ubf_block["gap_to_next_recognized_marker_bytes"] == 0x450

    for name in ("UBF_P", "SEQDAT_E", "SEQDAT_J", "SEQDAT_K"):
        row = by_name[name]
        assert all(marker["count_observed"] == 0 for marker in row["marker_counts_and_offsets"].values())
        # Absence of these signatures does not classify the file format.
        assert "no resource names are inferred from marker hits alone" in row["interpretation_limits"]
