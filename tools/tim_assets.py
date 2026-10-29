#!/usr/bin/env python3
"""Bounded decoder for the observed PlayStation TIM image formats.

The module intentionally keeps parsing and pixel conversion separate from
entity/sprite mapping. It does not claim that a decoded TIM is a complete
sprite or stage asset without the associated game metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
import struct
from typing import Final

TIM_MAGIC: Final[int] = 0x10
TIM_HEADER_SIZE: Final[int] = 8
BLOCK_HEADER_SIZE: Final[int] = 12
FLAG_CLUT: Final[int] = 0x08
ALLOWED_FLAGS: Final[int] = 0x0F


class TimFormatError(ValueError):
    """Raised when a TIM file is truncated, inconsistent, or unsupported."""


@dataclass(frozen=True)
class TimImage:
    image_x: int
    image_y: int
    width: int
    height: int
    pixel_mode: int
    has_clut: bool
    clut_x: int
    clut_y: int
    clut_width: int
    clut_height: int
    clut_words: tuple[int, ...]
    rgba: bytes
    image_block_length_style: str


def _u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def _block_length_style(declared: int, payload_size: int, label: str) -> str:
    if declared == payload_size + BLOCK_HEADER_SIZE:
        return "header-plus-payload"
    if declared == payload_size:
        return "payload-only"
    raise TimFormatError(f"{label} block length disagrees with dimensions")


def _expand5(value: int) -> int:
    value &= 0x1F
    return (value << 3) | (value >> 2)


def _color5551_to_rgba(color: int) -> bytes:
    red = _expand5(color)
    green = _expand5(color >> 5)
    blue = _expand5(color >> 10)
    # Raw zero is transparent; the PSX STP bit is represented as half alpha.
    alpha = 0 if color == 0 else (128 if color & 0x8000 else 255)
    return bytes((red, green, blue, alpha))


def decode_tim(data: bytes | bytearray | memoryview) -> TimImage:
    """Parse and decode one TIM to tightly packed RGBA8.

    Modes 0/1 use the first palette row in the retained CLUT. Modes 2/3 are
    direct-color. Both observed TIM image-block length conventions are accepted:
    block size including its 12-byte header, or payload size alone.
    """
    raw = bytes(data)
    if len(raw) < TIM_HEADER_SIZE:
        raise TimFormatError("TIM header is truncated")
    if _u32(raw, 0) != TIM_MAGIC:
        raise TimFormatError("invalid TIM magic")

    flags = _u32(raw, 4)
    if flags & ~ALLOWED_FLAGS:
        raise TimFormatError("unsupported TIM flag bits")
    mode = flags & 0x07
    has_clut = bool(flags & FLAG_CLUT)
    if mode > 3:
        raise TimFormatError("unsupported TIM pixel mode")
    if has_clut and mode >= 2:
        raise TimFormatError("CLUT is not valid for direct-color TIM mode")

    cursor = TIM_HEADER_SIZE
    clut_x = clut_y = clut_width = clut_height = 0
    clut_words: tuple[int, ...] = ()
    if has_clut:
        if len(raw) - cursor < BLOCK_HEADER_SIZE:
            raise TimFormatError("CLUT block header is truncated")
        declared = _u32(raw, cursor)
        clut_x, clut_y, clut_width, clut_height = struct.unpack_from("<HHHH", raw, cursor + 4)
        if clut_width == 0 or clut_height == 0:
            raise TimFormatError("CLUT dimensions are zero")
        entries = clut_width * clut_height
        payload_size = entries * 2
        _block_length_style(declared, payload_size, "CLUT")
        payload_offset = cursor + BLOCK_HEADER_SIZE
        if payload_offset > len(raw) or payload_size > len(raw) - payload_offset:
            raise TimFormatError("CLUT payload is truncated")
        clut_words = struct.unpack_from(f"<{entries}H", raw, payload_offset)
        cursor = payload_offset + payload_size

    if len(raw) - cursor < BLOCK_HEADER_SIZE:
        raise TimFormatError("image block header is truncated")
    image_declared = _u32(raw, cursor)
    image_x, image_y, word_width, height = struct.unpack_from("<HHHH", raw, cursor + 4)
    if word_width == 0 or height == 0:
        raise TimFormatError("image dimensions are zero")
    row_bytes = word_width * 2
    payload_size = row_bytes * height
    style = _block_length_style(image_declared, payload_size, "image")
    image_data_offset = cursor + BLOCK_HEADER_SIZE
    if image_data_offset > len(raw) or payload_size != len(raw) - image_data_offset:
        raise TimFormatError("image payload length does not match file size")

    if mode == 0:
        width = word_width * 4
        required_palette_entries = 16
    elif mode == 1:
        width = word_width * 2
        required_palette_entries = 256
    elif mode == 2:
        width = word_width
        required_palette_entries = 0
    else:
        if row_bytes % 3:
            raise TimFormatError("24bpp row byte count is not divisible by three")
        width = row_bytes // 3
        required_palette_entries = 0
    if width <= 0 or height <= 0:
        raise TimFormatError("decoded image dimensions are zero")
    if required_palette_entries and (not has_clut or clut_width < required_palette_entries or len(clut_words) < required_palette_entries):
        raise TimFormatError("indexed TIM does not contain a complete first palette")

    out = bytearray(width * height * 4)
    src = memoryview(raw)[image_data_offset : image_data_offset + payload_size]
    for y in range(height):
        src_row = src[y * row_bytes : (y + 1) * row_bytes]
        for x in range(width):
            dst_at = (y * width + x) * 4
            if mode == 0:
                packed = src_row[x // 2]
                palette_index = (packed >> 4) & 0x0F if x & 1 else packed & 0x0F
                rgba = _color5551_to_rgba(clut_words[palette_index])
            elif mode == 1:
                rgba = _color5551_to_rgba(clut_words[src_row[x]])
            elif mode == 2:
                rgba = _color5551_to_rgba(_u16(src_row, x * 2))
            else:
                base = x * 3
                rgba = bytes((src_row[base], src_row[base + 1], src_row[base + 2], 255))
            out[dst_at : dst_at + 4] = rgba

    return TimImage(
        image_x=image_x,
        image_y=image_y,
        width=width,
        height=height,
        pixel_mode=mode,
        has_clut=has_clut,
        clut_x=clut_x,
        clut_y=clut_y,
        clut_width=clut_width,
        clut_height=clut_height,
        clut_words=tuple(clut_words),
        rgba=bytes(out),
        image_block_length_style=style,
    )
