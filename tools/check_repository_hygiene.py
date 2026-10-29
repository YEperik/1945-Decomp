#!/usr/bin/env python3
"""Fail if original game media, extracted payloads, APKs, or Ghidra databases are tracked."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
MEDIA_EXTENSIONS = {
    ".7z", ".bin", ".cue", ".iso", ".elf", ".gzf", ".pss", ".tim",
    ".vag", ".adx", ".sq", ".hd", ".bd", ".gat", ".img", ".old",
    ".new", ".41", ".irx", ".apk", ".aab", ".so", ".o", ".a", ".class",
    ".gpr", ".jar", ".jks", ".keystore", ".zip",
}
EXCLUDED_ROOTS = {"source-media-working-copy", "extracted_disc", "ghidra-project"}
VERSION_SUFFIX = re.compile(r";\d+$")
MAX_TRACKED_BYTES = 15 * 1024 * 1024


def violations_for_paths(paths: Sequence[str], sizes: dict[str, int] | None = None) -> list[str]:
    violations: list[str] = []
    sizes = sizes or {}
    for raw in paths:
        rel = PurePosixPath(raw)
        if rel.parts and rel.parts[0] in EXCLUDED_ROOTS:
            if rel.name == ".gitkeep" and rel.parts[0] == "source-media-working-copy":
                continue
            violations.append(f"excluded media/database path tracked: {raw}")
            continue
        normalized = VERSION_SUFFIX.sub("", raw)
        extension = PurePosixPath(normalized).suffix.lower()
        if extension in MEDIA_EXTENSIONS:
            violations.append(f"excluded binary/media extension tracked: {raw}")
        size = sizes.get(raw)
        if size is not None and size >= MAX_TRACKED_BYTES:
            violations.append(f"unexpectedly large tracked file ({size} bytes): {raw}")
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        result = subprocess.run(
            ["git", "-C", str(args.repo), "ls-files", "-z"],
            check=True, capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: cannot list tracked files using Git: {exc}", file=sys.stderr)
        return 2
    paths = [item.decode("utf-8", errors="strict") for item in result.stdout.split(b"\0") if item]
    sizes: dict[str, int] = {}
    for raw in paths:
        try:
            sizes[raw] = (args.repo / raw).stat().st_size
        except OSError:
            pass
    violations = violations_for_paths(paths, sizes)
    print(json.dumps({"tracked_file_count": len(paths), "violations": violations,
                      "status": "failed" if violations else "passed"}, indent=2))
    if violations:
        return 1
    print("PASS: no excluded original game payloads or large binary artifacts are tracked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
