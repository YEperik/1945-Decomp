from __future__ import annotations

import csv
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
CATALOG = ROOT / "evidence/ezmidi_rpc_command_catalog.csv"


def test_ezmidi_rpc_dispatch_targets_and_payload_sizes_are_recorded() -> None:
    with CATALOG.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    by_id = {int(row["command_id"], 16): row for row in rows}

    assert len(rows) == 18
    assert len(by_id) == len(rows)
    assert by_id[0x9050]["iop_target"] == "MidiSetHd"
    assert by_id[0x9051]["masked_dispatch_id"] == "0x9050"
    assert by_id[0x9051]["argument_nibble"] == "1"
    assert by_id[0x9060]["iop_target"] == "MidiTransBdPacket"
    assert by_id[0x9080]["iop_target"] == "MidiGetIopFileLength"
    assert by_id[0x9080]["ee_request_bytes"] == "64"
    assert by_id[0x9080]["ee_response_bytes"] == "64"
    assert by_id[0x8010]["iop_target"] == "MidiInit"
    assert 0x0010 not in by_id  # Dispatcher explicitly compares 0x8010, not 0x0010.
    assert by_id[0x00A0]["iop_target"] == "MidiSetPortAttr"
    assert by_id[0x00A1]["masked_dispatch_id"] == "0x00A0"
    assert by_id[0x00B0]["iop_target"] == "MidiSetPortVolume"
    assert by_id[0x00B1]["masked_dispatch_id"] == "0x00B0"
