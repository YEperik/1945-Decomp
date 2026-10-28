#!/usr/bin/env bash
# Run R5900-aware headless analysis without executing or modifying the ELF.
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
LANGUAGE_ID="r5900:LE:32:default"
BOOT_PATH="SLES_517.41;1"
EXPECTED_ENTRY="0x00100008"

usage() {
  cat >&2 <<USAGE
Usage:
  GHIDRA_HOME=/path/to/ghidra_12.1.4 $0 /path/to/disc-image.bin [output-directory]

Requirements:
  * Ghidra 12.1.4 with Emotion Engine: Reloaded v2.1.38 installed/enabled
  * Language ID available: ${LANGUAGE_ID}
  * Java compatible with that Ghidra release

The output directory must be outside the repository. The extracted ELF is
kept in a temporary directory and removed when analysis exits.
USAGE
}

if [[ $# -lt 1 || $# -gt 2 ]]; then usage; exit 2; fi
IMAGE_PATH="$(realpath -- "$1")"
if [[ ! -f "$IMAGE_PATH" ]]; then echo "ERROR: disc image not found: $IMAGE_PATH" >&2; exit 2; fi
if [[ -z "${GHIDRA_HOME:-}" ]]; then
  echo "BLOCKED: GHIDRA_HOME is not set; Ghidra is not bundled with this repository." >&2
  usage
  exit 3
fi
GHIDRA_HOME="$(realpath -- "$GHIDRA_HOME")"
HEADLESS="$GHIDRA_HOME/support/analyzeHeadless"
if [[ ! -x "$HEADLESS" ]]; then
  echo "ERROR: analyzeHeadless not found or not executable: $HEADLESS" >&2
  exit 3
fi

# Verify the installed processor definition instead of guessing a language ID.
SEARCH_ROOTS=("$GHIDRA_HOME")
if [[ -d "$HOME/.ghidra" ]]; then SEARCH_ROOTS+=("$HOME/.ghidra"); fi
if ! find "${SEARCH_ROOTS[@]}" -type f -name '*.ldefs' -print0 2>/dev/null |
     xargs -0 -r grep -lF -- "id=\"$LANGUAGE_ID\"" >/dev/null; then
  echo "BLOCKED: processor language ID $LANGUAGE_ID was not found in the Ghidra installation/user extension files." >&2
  echo "Install/enable Emotion Engine: Reloaded and retry; no generic MIPS fallback is used." >&2
  exit 4
fi

OUTPUT_DIR="$(realpath -m -- "${2:-${TMPDIR:-/tmp}/1945-ghidra-r5900-output}")"
case "$OUTPUT_DIR" in
  "$ROOT_DIR"|"$ROOT_DIR"/*)
    echo "ERROR: Ghidra project/output must be outside the repository to prevent importing the original ELF into Git." >&2
    exit 2
    ;;
esac
mkdir -p -- "$OUTPUT_DIR"
EXPORT_DIR="$OUTPUT_DIR/exports"
PROJECT_DIR="$OUTPUT_DIR/project"
LOG_DIR="$OUTPUT_DIR/logs"
mkdir -p -- "$EXPORT_DIR" "$PROJECT_DIR" "$LOG_DIR"
TMP_DIR="$(mktemp -d -t 1945-ghidra-XXXXXX)"
trap 'rm -rf -- "$TMP_DIR"' EXIT

PYTHONPATH="$ROOT_DIR/tools${PYTHONPATH:+:$PYTHONPATH}" python3 - "$IMAGE_PATH" "$TMP_DIR/boot.elf" "$BOOT_PATH" <<'PY'
import sys
from pathlib import Path
from elf_recon import inspect_boot_elf
image_path, output_path, boot_path = map(Path, sys.argv[1:])
report, payload = inspect_boot_elf(image_path, str(boot_path))
if report["elf"]["entry_point"] != 0x00100008:
    raise SystemExit(f"Unexpected ELF entry point: 0x{report['elf']['entry_point']:08x}")
Path(output_path).write_bytes(payload)
print(f"boot_path={report['boot_path']}")
print(f"boot_sha256={report['boot_sha256']}")
print(f"entry_point=0x{report['elf']['entry_point']:08x}")
print(f"elf_bytes={len(payload)}")
PY

"$HEADLESS" "$PROJECT_DIR" "1945_SLES_51741" \
  -import "$TMP_DIR/boot.elf" \
  -processor "$LANGUAGE_ID" \
  -overwrite \
  -scriptPath "$ROOT_DIR/ghidra_scripts" \
  -analysisTimeoutPerFile 900 \
  -postScript Export1945Evidence.java "$EXPORT_DIR" "$EXPECTED_ENTRY" \
  -log "$LOG_DIR/analyze.log" \
  -scriptlog "$LOG_DIR/script.log"

if [[ ! -s "$EXPORT_DIR/ghidra_functions.csv" || ! -s "$EXPORT_DIR/ghidra_call_references.csv" || ! -s "$EXPORT_DIR/ghidra_selected_disassembly.csv" || ! -s "$EXPORT_DIR/ghidra_metadata.txt" ]]; then
  echo "ERROR: headless process returned but one or more evidence exports are missing/empty." >&2
  exit 5
fi
if ! grep -qx "language_id=$LANGUAGE_ID" "$EXPORT_DIR/ghidra_metadata.txt"; then
  echo "ERROR: exported metadata does not confirm the required R5900 language ID." >&2
  exit 5
fi
if ! grep -qx 'expected_entry_instruction_present=true' "$EXPORT_DIR/ghidra_metadata.txt"; then
  echo "ERROR: Ghidra did not produce a decoded instruction at expected ELF entry $EXPECTED_ENTRY." >&2
  exit 5
fi
for csv_file in ghidra_functions.csv ghidra_call_references.csv ghidra_selected_disassembly.csv; do
  line_count="$(wc -l < "$EXPORT_DIR/$csv_file")"
  if (( line_count <= 1 )); then
    echo "ERROR: $csv_file contains only its header; refusing to report a successful analysis." >&2
    exit 5
  fi
done
printf 'Ghidra analysis outputs: %s\n' "$OUTPUT_DIR"
printf 'Temporary ELF removed on exit; source disc image unchanged.\n'
