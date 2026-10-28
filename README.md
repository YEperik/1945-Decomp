# 1945 Native Android Port — Baseline Repository

This repository is a **baseline/checkpoint**, not a completed port. It records the initial environment inspection and the first verifiable facts about the supplied disc-image archive. No gameplay implementation has been started.

## Current evidence

- The uploaded 7z archive was readable with the installed `libarchive` C API.
- The archive contains a `.bin` image and a `.cue` file; both were extracted into `source-media-working-copy/` and the extracted byte counts matched the archive metadata.
- SHA-256 values and the archive listing are saved in `evidence/`.
- The CUE declares one `MODE2/2352` track. A read-only scanner found a `PLAYSTATION` volume descriptor, a PAL `SYSTEM.CNF` referencing `SLES_517.41;1`, and a matching MIPS ELF boot executable. These facts corroborate the requested target, but do not prove authenticity.
- `tools/disc_inventory.py` creates a raw-sector and file-level inventory; see `evidence/disc_inventory.json` and `evidence/disc_file_manifest.csv`.
- Android SDK/NDK, Gradle, ADB, and a 7z CLI were not found in the inspected environment locations/command path. `libarchive` is available for archive listing and extraction.

## Start here

1. Read [`PROJECT_STATUS.md`](PROJECT_STATUS.md).
2. Read [`REVERSE_ENGINEERING_NOTES.md`](REVERSE_ENGINEERING_NOTES.md) for verified facts and the current hypotheses/gaps.
3. Read [`KNOWN_ISSUES.md`](KNOWN_ISSUES.md) for blockers.
4. Read [`BUILD_AND_RELEASE.md`](BUILD_AND_RELEASE.md) before attempting an Android build.

## Media boundary

The source archive remains at its uploaded location, outside this repository. The extracted `.bin` and `.cue` are a local working copy and are ignored by Git. Do not publish original game media or proprietary extracted assets without authorization.

## Archive helper tools

`tools/archive_inventory.c` and `tools/extract_1945.c` are small `libarchive`-based inspection helpers. They do not implement any game behavior. Build on a Linux host with libarchive development headers installed, for example:

```sh
cc -Wall -Wextra -Werror tools/archive_inventory.c -larchive -o /tmp/archive_inventory
/tmp/archive_inventory "/path/to/archive.7z"
```

The extraction helper deliberately accepts only the two expected base filenames and writes them to a caller-specified working directory. Review it before using it on an archive from another source.
