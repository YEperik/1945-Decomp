# Project Status

**Snapshot date:** 2026-10-28
**Status:** Phase 0 baseline established and initial disc inventory completed; native port not started.
**Checkpoint:** Initial baseline commit `476814d` established the evidence-only repository. The current follow-up checkpoint adds raw-sector/file inventory tooling, asset-signature probes and regression tests.

## 1. Completed work

- Inspected `/mnt/data` and confirmed that no pre-existing source repository or `.git` directory was supplied in the inspected workspace paths.
- Identified the uploaded archive as 7-Zip format (`file` reports 7-zip archive data, version 0.3).
- Computed SHA-256 of the unchanged uploaded archive: `d76bdffa6254d82d05bca248fd7a536f002d7f5c897c683a06d61d4dd8d52412`.
- Used `libarchive`'s 7-Zip reader to enumerate two entries; see `evidence/archive_inventory.tsv`.
- Extracted a working copy using a bounded helper which allows only the two expected filenames; both byte counts matched archive-reported sizes.
- Computed SHA-256 of the extracted image and CUE; see `evidence/input_sha256.txt`.
- Read the CUE file. It describes one `MODE2/2352` track beginning at `INDEX 01 00:00:00`.
- Implemented and ran `tools/disc_inventory.py` against all 80,880 sectors. Its bounded read-only scan recorded zero sync, mode, MSF, or duplicated-subheader inconsistencies.
- Read ISO9660-style primary volume descriptor at LBA 16 and terminator at LBA 17. The volume reports `PLAYSTATION`, 80,880 logical blocks of 2,048 bytes, and a root directory at LBA 22.
- Walked the directory records and produced hashes for 659 files under the volume. 37 directory entries were inventoried (excluding the root). No directory parsing/content-hash errors were reported.
- Inspected `SYSTEM.CNF;1`: `BOOT2 = cdrom0:\SLES_517.41;1`, `VER = 1.00`, `VMODE = PAL`.
- Identified the referenced boot executable at LBA 61. Its 2,352,776-byte payload hashes to `7d69a626ca65265e573a18633b90519f80906c82e62e41a60ea697a8f149d3a1`; `readelf` confirms ELF32 little-endian MIPS executable metadata, entry `0x00100008`, three program headers, and flags `0x20924001` (including `5900`, `eabi64`, `mips3`). The executable was inspected from a temporary file and was not committed.
- Ran sample signature probes on two `.PSS` files and one `.TIM` file. `file`/`ffprobe` identify the two PSS samples as MPEG program streams with MPEG-2 video (640×448, 30000/1001 fps, 9.009 s); `file` identifies the sampled TIM as a 320×240 8-bit TIM image with 256 CLUT entries. The probes were extracted only to `/tmp` and are not committed.
- Created baseline documentation, evidence, tests, and tools. The game media is excluded from version control. The current follow-up changes are recorded in Git; the exact HEAD is given in the final engineering report.

## 2. Verified baseline

### Input archive and extracted members

| Item | Value | Evidence / interpretation |
|---|---:|---|
| Uploaded archive size | 52,389,816 bytes | `ls -l` |
| Uploaded archive SHA-256 | `d76bdffa6254d82d05bca248fd7a536f002d7f5c897c683a06d61d4dd8d52412` | `evidence/input_sha256.txt` |
| `.bin` size in archive and extracted copy | 190,229,760 bytes | `libarchive` listing and extraction byte-count report |
| `.cue` size in archive and extracted copy | 103 bytes | `libarchive` listing and extraction byte-count report |
| Track declaration | One `MODE2/2352` track | Extracted CUE text |
| `.bin` raw sector count | 80,880 × 2,352-byte sectors | Full raw-sector header scan; zero recorded sync/mode/MSF/subheader inconsistencies |
| Filesystem descriptor | LBA 16 primary descriptor; LBA 17 terminator | `CD001`, version 1; system ID `PLAYSTATION` |
| ISO logical volume | 80,880 × 2,048-byte blocks | Both-endian volume/block-size fields agree |
| File inventory | 659 files, 37 directory entries plus root | File payload SHA-256 computed from raw sectors; zero inventory/hash errors |
| Boot config | `SLES_517.41;1`, `VMODE = PAL`, version `1.00` | Read-only parse of `SYSTEM.CNF;1` |
| Boot executable | `SLES_517.41;1`, 2,352,776 bytes | ELF32 LE, MIPS machine 8, entry `0x00100008`, 3 program headers; see `evidence/primary_elf_header.txt` |
| Tail sectors | LBA 80730–80879 (150 sectors) | Mode 2 headers remain structured; XA submode is `0x00` and 2,048-byte user area is all zero. Likely padding/non-data tail is a hypothesis, not a validated disc-format conclusion. |

The archive and file hashes establish a reproducible local baseline, not authenticity or publisher provenance. The boot configuration strongly corroborates the declared `SLES-51741` PAL target, but does not prove the image is authentic or byte-identical to a trustworthy reference. Raw sector EDC/ECC checks, path-table cross-validation, overlap analysis, and reference checksum comparison remain outstanding.

### Tooling environment

| Component | Observation | Status |
|---|---|---|
| OS | Debian GNU/Linux 13.3 (trixie), x86_64 Linux | Verified |
| C compiler | Clang 17.0.0, host target `x86_64-unknown-linux-gnu` | Available; not an Android cross-compiler |
| Java | OpenJDK 21.0.12.1 | Available |
| CMake | 3.31.6 | Available |
| Git | 2.47.3 | Available |
| Ninja | Found in PATH | Available |
| libarchive | 3.7.4; shared library present; C helpers compile and run linked against `-larchive` | Verified for archive inventory/extraction |
| Python / pytest | Present; 11 unit tests currently pass | Available for parser regression tests |
| Android SDK / NDK | Not found in inspected standard locations; related environment variables not set | Blocker for Android build in this environment |
| Gradle / ADB / sdkmanager / avdmanager / ndk-build | Not found in PATH | Blocker for Android build/device testing |
| `7z`, `7zz`, `7zr`, `bsdtar`, `unar` | Not found in PATH | Workaround: `libarchive` C API succeeded |
| Ghidra / IDA | Not found in inspected standard locations/PATH | Static analysis environment not established |
| Pre-existing code repository | None found in inspected workspace paths | No application source or history was available to inspect |

## 3. Verification evidence

- `file` identified the input as a 7-Zip archive.
- `sha256sum` recorded checksums.
- `tools/archive_inventory.c`, compiled with `cc -Wall -Wextra -Werror ... -larchive`, read the archive to EOF and enumerated exactly two entries totalling 190,229,863 reported uncompressed bytes.
- `tools/extract_1945.c` extracted exactly two expected files and reported output sizes matching archive metadata.
- `tools/disc_inventory.py` ran successfully: 80,880 sector headers scanned, zero recorded header findings, 659 file hashes computed, and zero inventory/content-hash errors.
- `pytest -q`: 11 parser/helper unit tests passed.
- `file` and `readelf -h/-l` independently inspect the extracted-to-`/tmp` boot executable. It was not executed.
- The `SYSTEM.CNF` values and ELF metadata are recorded in `evidence/system_cnf_summary.txt` and `evidence/primary_elf_header.txt`. Sample media format probes are recorded in `evidence/asset_signature_observations.md`.

These checks do not validate CD-ROM EDC/ECC, compare the path tables against the walked directory tree, detect every possible overlapping extent, establish provenance, decode texture/audio/custom data formats, reconstruct functions, or validate gameplay behavior.

## 4. Defects / blockers found

See `KNOWN_ISSUES.md`. The primary immediate blockers are absence of Android build/device tooling and absence of an existing source repository. Boot metadata and the main ELF have been identified; reference authenticity, sector EDC/ECC, complete format validation and gameplay reconstruction remain outstanding.

## 5. Tests and build status

- Archive listing: **passed** for the supplied file using `libarchive`.
- Archive extraction: **passed** for exactly two expected members; byte counts matched archive metadata.
- SHA-256 recording: **passed**.
- Basic raw sector header consistency: **passed with zero recorded findings** for 80,880 sectors.
- ISO-style directory inventory and file content hashes: **passed within the parser's supported format**, 659 files and zero reported parse/hash errors.
- Boot config and ELF header inspection: **passed**; exact results are recorded in `evidence/`.
- CD-ROM EDC/ECC and full filesystem conformance: **not run**. Sample PSS/TIM formats have been identified, but the remaining asset formats/decoders and visual/audio validation are **not run**.
- Existing project build: **not applicable; no project was supplied**.
- Android build, install, run, gameplay and regression tests: **not run**.

## 6. Project integrity

- Source/media archive was not modified.
- Extracted media is a working copy and ignored by Git.
- Baseline code does not contain a game runtime or production port implementation.
- Repository snapshot includes the current engineering changes in Git; `git status` is checked after the checkpoint commit.
- No Android release artifact exists.
