from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import static_control_flow as scf  # noqa: E402


def encode_j(opcode: int, target: int) -> int:
    return (opcode << 26) | ((target >> 2) & 0x03FFFFFF)


def encode_branch(opcode: int, pc: int, target: int, rt: int = 0, rs: int = 0) -> int:
    displacement = (target - (pc + 4)) // 4
    assert -32768 <= displacement <= 32767
    return (opcode << 26) | (rs << 21) | (rt << 16) | (displacement & 0xFFFF)


def test_decode_jal_target_and_delay_slot():
    pc = 0x00100008
    target = 0x001BDF38
    decoded = scf.decode_control_transfer(encode_j(3, target), pc)
    assert decoded is not None
    assert decoded["kind"] == "direct_call"
    assert decoded["target"] == target
    assert decoded["delay_slot_address"] == pc + 4


def test_decode_direct_jump():
    pc = 0x001001C0
    target = 0x001BE320
    decoded = scf.decode_control_transfer(encode_j(2, target), pc)
    assert decoded is not None
    assert decoded["kind"] == "direct_jump"
    assert decoded["target"] == target


def test_decode_negative_branch_displacement():
    pc = 0x00184F10
    target = 0x00184EA8
    decoded = scf.decode_control_transfer(encode_branch(0x04, pc, target), pc)
    assert decoded is not None
    assert decoded["kind"] == "conditional_branch"
    assert decoded["target"] == target


def test_decode_regimm_branch_and_link():
    pc = 0x00100000
    target = 0x00100100
    word = encode_branch(0x01, pc, target, rt=0x11, rs=4)
    decoded = scf.decode_control_transfer(word, pc)
    assert decoded is not None
    assert decoded["kind"] == "conditional_call"
    assert decoded["target"] == target


def test_decode_return_and_indirect_call():
    # jr $ra (rs=31, funct=8)
    ret = scf.decode_control_transfer((31 << 21) | 0x08, 0x00100010)
    assert ret is not None and ret["kind"] == "return"
    # jalr $ra,$t9 (rd=31, rs=25, funct=9)
    jalr = scf.decode_control_transfer((25 << 21) | (31 << 11) | 0x09, 0x00100020)
    assert jalr is not None and jalr["kind"] == "indirect_call"
    assert jalr["rs"] == 25 and jalr["rd"] == 31


def test_non_control_instruction_returns_none():
    # addiu $sp, $sp, -0x10
    assert scf.decode_control_transfer(0x27BDFFF0, 0x00100000) is None


def test_branch_wrap_math_uses_pc_relative_base():
    pc = 0x00100000
    decoded = scf.decode_control_transfer(encode_branch(0x05, pc, 0x00100008, rs=2, rt=3), pc)
    assert decoded is not None and decoded["target"] == 0x00100008


def test_executable_regions_exclude_unmapped_dvp_overlay():
    elf = {
        "sections": [
            {"index": 1, "name": ".text", "flags": 0x6, "type": 1,
             "address": 0x100000, "file_offset": 0x1000, "size": 0x100},
            {"index": 2, "name": ".DVP.overlay.example", "flags": 0x5,
             "type": 0x7FFFF821, "address": 0, "file_offset": 0x2000, "size": 0x100},
        ]
    }
    regions = scf.executable_regions(elf)
    assert regions[0]["scan_status"] == "scanned"
    assert regions[1]["scan_status"] == "excluded_unmapped_overlay"


def test_executable_regions_keep_nonzero_named_code_sections():
    elf = {
        "sections": [
            {"index": 1, "name": ".gnu.linkonce.t.SetRGB", "flags": 0x6, "type": 1,
             "address": 0x1DB3D8, "file_offset": 0xDC3D8, "size": 0x24},
        ]
    }
    regions = scf.executable_regions(elf)
    assert len(regions) == 1
    assert regions[0]["scan_status"] == "scanned"


def test_excluded_overlay_virtual_overlap_is_recorded_not_scanned():
    elf = {
        "entry_point": 0x100000,
        "sections": [
            {"index": 1, "name": ".text", "flags": 0x6, "type": 1,
             "address": 0x100000, "file_offset": 0, "size": 8},
            {"index": 2, "name": ".DVP.overlay.a", "flags": 0x5,
             "type": 0x7FFFF821, "address": 0, "file_offset": 8, "size": 0x20},
            {"index": 3, "name": ".DVP.overlay.b", "flags": 0x5,
             "type": 0x7FFFF821, "address": 0, "file_offset": 40, "size": 0x10},
        ]
    }
    result = scf.analyze_control_flow(elf, b"\x00" * 64)
    assert result["executable_section_overlap_findings"] == []
    assert len(result["excluded_region_overlap_findings"]) == 1
    overlap = result["excluded_region_overlap_findings"][0]
    assert overlap["section_a"] == ".DVP.overlay.a"
    assert overlap["section_b"] == ".DVP.overlay.b"
    assert overlap["overlap_start"] == "0x00000000"
    assert overlap["overlap_end_exclusive"] == "0x00000010"
