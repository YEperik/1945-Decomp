from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from probe_ps2_sound_blocks import ProbeError, probe_bytes, probe_file  # noqa: E402


def test_p_bav_candidate_size_ends_at_next_p_bav_marker() -> None:
    block1 = b"pBAV" + (7).to_bytes(4, "little") + (0).to_bytes(4, "little") + (24).to_bytes(4, "little")
    data = block1 + b"x" * 8 + b"pBAV" + b"\x00" * 12 + b"pQES"
    result = probe_bytes("synthetic", data)
    headers = result["pBAV_candidate_headers"]
    assert result["marker_counts_and_offsets"]["pBAV"]["count_observed"] == 2
    assert headers[0]["candidate_size_u32"] == 24
    assert headers[0]["candidate_end_offset_hex"] == "0x18"
    assert headers[0]["candidate_size_in_bounds"] is True
    assert headers[0]["next_recognized_marker_at_or_after_candidate_end"]["offset_hex"] == "0x18"


def test_p_bav_out_of_bounds_size_is_flagged_not_followed() -> None:
    data = b"pBAV" + (7).to_bytes(4, "little") + (0).to_bytes(4, "little") + (0xFFFF).to_bytes(4, "little")
    result = probe_bytes("synthetic", data)
    record = result["pBAV_candidate_headers"][0]
    assert record["candidate_size_in_bounds"] is False
    assert record["next_recognized_marker_at_or_after_candidate_end"] is None


def test_missing_signatures_are_zero_count_and_hash_is_reported() -> None:
    data = b"no known sound markers\x00"
    result = probe_bytes("synthetic", data, hashlib.sha256(data).hexdigest())
    assert all(item["count_observed"] == 0 for item in result["marker_counts_and_offsets"].values())
    assert result["expected_sha256_matches"] is True


def test_expected_hash_mismatch_is_visible() -> None:
    result = probe_bytes("synthetic", b"abc", "0" * 64)
    assert result["expected_sha256_matches"] is False


def test_probe_file_rejects_over_limit(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "large.bin"
    path.write_bytes(b"12345")
    with pytest.raises(ProbeError, match="greater than max_bytes"):
        probe_file("large", path, None, max_bytes=4)


def test_cli_writes_metadata_report_without_copying_input(tmp_path: pathlib.Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"pBAV" + (7).to_bytes(4, "little") + b"\x00" * 4 + (16).to_bytes(4, "little"))
    output = tmp_path / "evidence" / "probe.json"
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    completed = subprocess.run(
        [sys.executable, str(ROOT / "tools/probe_ps2_sound_blocks.py"),
         "--input", f"test={source}", "--expected-sha256", f"test={digest}", "--output", str(output)],
        check=True, text=True, capture_output=True,
    )
    parsed = json.loads(output.read_text(encoding="utf-8"))
    assert parsed["input_count"] == 1
    assert parsed["reports"][0]["expected_sha256_matches"] is True
    assert "pBAV" in completed.stdout
    assert source.stat().st_size == 16


def test_compact_directory_candidate_is_reported_without_inventing_spans() -> None:
    # count=2, directory size=20; targets are monotonic, first points at its end.
    data = (
        (2).to_bytes(4, "little")
        + (20).to_bytes(4, "little") + (ord("1")).to_bytes(4, "little")
        + (28).to_bytes(4, "little") + (ord("8")).to_bytes(4, "little")
        + b"pQES" + b"xxxx" + b"pBAV"
    )
    result = probe_bytes("synthetic", data)
    table = result["compact_directory_table_candidate"]
    assert table["detected"] is True
    assert table["directory_size_candidate_bytes"] == 20
    assert table["entries"][0]["recognized_marker_at_target"] == "pQES"
    assert table["entries"][1]["recognized_marker_at_target"] == "pBAV"
    assert "span" not in table["entries"][0]


def test_compact_directory_candidate_does_not_accept_non_monotonic_targets() -> None:
    data = (
        (2).to_bytes(4, "little")
        + (20).to_bytes(4, "little") + (1).to_bytes(4, "little")
        + (16).to_bytes(4, "little") + (2).to_bytes(4, "little")
        + b"x" * 16
    )
    result = probe_bytes("synthetic", data)
    assert result["compact_directory_table_candidate"]["detected"] is False


def test_context_strings_are_recorded_as_hints_not_classifications() -> None:
    data = b"RECTDT  SEQUENCE\x00PALETTE BGMAPTBL\x00BGMAP   OBJDT"
    result = probe_bytes("context", data)
    contexts = result["context_string_hits"]
    assert contexts["RECTDT  SEQUENCE"]["count_observed"] == 1
    assert contexts["PALETTE BGMAPTBL"]["count_observed"] == 1
    assert contexts["BGMAP   OBJDT"]["count_observed"] == 1
    assert "classification" not in contexts["BGMAP   OBJDT"]
