# Reverse-Engineering Notes

**Target as declared by the request:** *1945 I & II: The Arcade Games*, PAL, disc ID `SLES-51741`. The image metadata now corroborates the requested identifier/region through `SYSTEM.CNF` (`SLES_517.41;1`, `VMODE = PAL`), but source authenticity and reference-image identity remain unverified.

## Evidence record: input archive

- Archive: `1945 I & II (Europe) (En,Fr,De,Es,It).7z`
- Archive format: 7-Zip, as reported by `file` and accepted by libarchive's 7-Zip reader.
- Archive SHA-256: `d76bdffa6254d82d05bca248fd7a536f002d7f5c897c683a06d61d4dd8d52412`
- Member list: `evidence/archive_inventory.tsv`
- Recorded hashes: `evidence/input_sha256.txt`
- Members: one `.bin` file (190,229,760 bytes) and one `.cue` file (103 bytes).
- Extraction: both members extracted to `source-media-working-copy/`; extracted sizes matched metadata.
- CUE text: one `MODE2/2352` binary track, `INDEX 01 00:00:00`.
- BIN size is divisible by 2,352 bytes: 80,880 nominal raw sectors. This arithmetic is not a sector-integrity check.

## Additional disc and executable evidence

- Raw-sector checks: 80,880 × 2,352-byte sectors; zero recorded sync mismatches, non-Mode-2 sectors, invalid/mismatched MSF addresses, or duplicated-subheader differences.
- Volume descriptors: primary descriptor at LBA 16 and terminator at LBA 17, both `CD001` version 1. The primary descriptor's system ID is `PLAYSTATION`; the volume has 80,880 logical blocks of 2,048 bytes and a root directory extent at LBA 22 of 2,048 bytes.
- Boot config: ISO path `SYSTEM.CNF;1`; SHA-256 `babfbc73351dacd132bad6d44e2cb25c65f66e67b6f3d2a8c34c01a49b244c6d`; parsed fields include `BOOT2 = cdrom0:\SLES_517.41;1`, `VER = 1.00`, `VMODE = PAL`.
- Referenced executable: ISO path `SLES_517.41;1`, data LBA 61, size 2,352,776 bytes, SHA-256 `7d69a626ca65265e573a18633b90519f80906c82e62e41a60ea697a8f149d3a1`.
- ELF header: ELF32, little-endian, `ET_EXEC`, `EM_MIPS`, entry `0x00100008`, three program headers, 301 section headers, flags `0x20924001`; GNU `readelf` reports MIPS-III and flags that include `5900`, `eabi64`, and `mips3`. This is consistent with the intended PS2 EE executable. It was inspected, not executed.
- Other ELF signatures: 14 additional files under `MODULES/` begin with ELF magic. Their architecture/roles have not yet been fully validated.
- Sample assets: `PSS/ROGO0.PSS;1` and `PSS/SIG2.PSS;1` are recognized as MPEG program streams; `ffprobe` reports MPEG-2 video 640×448 at 30000/1001 fps and 9.009 s for each. `PSS/LOADING1.TIM;1` is recognized by `file` as a PlayStation TIM image (8-bit 320×240, 256 CLUT entries). These are sample-level observations only, not a full asset-decoder validation. See `evidence/asset_signature_observations.md`.
- File inventory: 659 file records hashed (164,148,582 bytes in aggregate file-record lengths), with 37 directory entries plus root; no parser/content-hash errors were reported.
- Tail observation: the observed all-zero submode run spans LBA 80730 through 80879 inclusive (150 sectors). These sectors retain recognizable raw-sector sync/MSF/mode headers but have XA submode `0x00` and all-zero 2,048-byte user areas. Treat “padding/non-data tail” only as a hypothesis until format checks/reference comparison are complete.

## Confidence classifications

### Verified

- The archive can be read by the installed libarchive 7-Zip reader.
- All 80,880 raw-sector headers pass the current sync/mode/MSF/duplicated-subheader checks; EDC/ECC is expressly outside the current scanner.
- The ISO-style volume descriptor, directory walk, file content hashes and `SYSTEM.CNF` fields are reproducibly recorded in `evidence/`.
- `SYSTEM.CNF;1` names `SLES_517.41;1` as the boot file and specifies `VMODE = PAL`.
- The boot file is a parsed ELF32 little-endian MIPS executable; its metadata was inspected without running it.
- The archive enumerates exactly the two members above.
- Extracted member byte counts match archive-reported lengths.
- The extracted CUE declares a single `MODE2/2352` track.
- The supplied archive and extracted files have the SHA-256 values in `evidence/input_sha256.txt`.

### Strongly inferred

- The image is consistent with the requested PAL `SLES-51741` target: `SYSTEM.CNF;1` references `SLES_517.41;1`, sets `VMODE = PAL`, and that file is an ELF32 little-endian MIPS executable with flags indicating MIPS III / 5900.
- The `.bin` and `.cue` are intended to form a raw CD image pair, based on the CUE `FILE` declaration and `MODE2/2352` track declaration. File-size arithmetic and raw-sector headers are consistent, but complete media conformance and provenance remain unverified.

### Hypotheses / unresolved

- Whether the disc is complete, authentic, unmodified, or byte-identical to a trustworthy reference.
- Whether raw sector EDC/ECC checksums are correct, especially around the final 150 all-zero user-data sectors.
- Whether path tables match the directory walk and whether any file extents overlap or rely on special disc conventions.
- The actual formats of most `.TIM`, `.BIN`, `.SQ`, `.BD`, `.HD`, `.GAT`, and other non-ELF files; only two PSS and one TIM sample have been probed in detail, and names/extensions are not proof of encoding.
- All gameplay functions, data structures, graphics/audio decoding, timing and simulation behavior.

## Next smallest useful experiments

1. Add CD-ROM EDC/ECC verification and check the 150 trailing sectors without trimming or modifying them.
2. Cross-check primary/optional path tables against the walked directory records and implement explicit extent-overlap and multi-extent detection.
3. Establish a Ghidra/IDA environment with correct MIPS/R5900 handling; analyze the boot executable entry path and build an evidence-linked function map.
4. Classify asset formats from signatures, sizes, references and candidate loader code before writing decoders; use independent decoders/reference observations where possible.
5. Obtain or establish a lawful reference environment and capture deterministic behavior before reconstructing simulation and rendering.

## Method restrictions

Do not execute the original PS2 ELF as the final runtime. Do not describe a guessed texture/audio format or a guessed function purpose as verified. Keep original media read-only and keep extracted copyrighted content out of public source control unless authorized.
