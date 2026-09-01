#!/usr/bin/env python3
"""Convert full CSI binary records into verified HPE multi-record text chunks."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


RECORD_BYTES = 8192
WORDS_PER_LINE = 8


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def format_record(payload: bytes) -> str:
    if len(payload) != RECORD_BYTES:
        raise ValueError(f"record contains {len(payload)} bytes; expected {RECORD_BYTES}")
    words = [
        int.from_bytes(payload[offset : offset + 4], "little")
        for offset in range(0, RECORD_BYTES, 4)
    ]
    lines = ["CSI record:"]
    for offset in range(0, len(words), WORDS_PER_LINE):
        lines.append(
            "".join(f"0x{word:08x}\t" for word in words[offset : offset + 8])
        )
    return "\n".join(lines) + "\n"


def rebuild_text(text: str) -> bytes:
    rebuilt = bytearray()
    records = 0
    words_in_record = 0
    for line_number, line in enumerate(text.splitlines(), start=1):
        if line == "CSI record:":
            if records and words_in_record != RECORD_BYTES // 4:
                raise ValueError(
                    f"record {records - 1} has {words_in_record} words"
                )
            records += 1
            words_in_record = 0
            continue
        if not line.strip():
            continue
        if records == 0:
            raise ValueError(f"data before first record marker at line {line_number}")
        for token in line.split():
            if not token.startswith("0x") or len(token) != 10:
                raise ValueError(f"invalid word at line {line_number}: {token}")
            rebuilt.extend(int(token, 16).to_bytes(4, "little"))
            words_in_record += 1
    if records == 0:
        raise ValueError("no CSI record markers")
    if words_in_record != RECORD_BYTES // 4:
        raise ValueError(f"record {records - 1} has {words_in_record} words")
    return bytes(rebuilt)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path, help="full-record binary capture")
    parser.add_argument("output_dir", type=Path, help="output directory")
    parser.add_argument(
        "--records-per-file",
        type=int,
        default=100,
        help="records per text file (default: 100)",
    )
    args = parser.parse_args()
    if args.records_per_file < 1:
        parser.error("--records-per-file must be positive")

    source = args.capture.read_bytes()
    if not source or len(source) % RECORD_BYTES:
        raise SystemExit(
            f"{args.capture}: {len(source)} bytes is not a nonempty multiple "
            f"of {RECORD_BYTES}"
        )
    total_records = len(source) // RECORD_BYTES
    args.output_dir.mkdir(parents=True, exist_ok=True)

    parts: list[dict[str, object]] = []
    for part, first in enumerate(
        range(0, total_records, args.records_per_file), start=1
    ):
        stop = min(total_records, first + args.records_per_file)
        last = stop - 1
        source_part = source[first * RECORD_BYTES : stop * RECORD_BYTES]
        text = "".join(
            format_record(source[offset : offset + RECORD_BYTES])
            for offset in range(first * RECORD_BYTES, stop * RECORD_BYTES, RECORD_BYTES)
        )
        name = (
            f"{args.capture.stem}.part-{part:03d}."
            f"records-{first:06d}-{last:06d}.txt"
        )
        path = args.output_dir / name
        path.write_text(text, encoding="ascii", newline="\n")

        rebuilt = rebuild_text(path.read_text(encoding="ascii"))
        if rebuilt != source_part:
            raise RuntimeError(f"round-trip verification failed for {name}")
        parts.append(
            {
                "part": part,
                "file": name,
                "first_record": first,
                "last_record": last,
                "records": stop - first,
                "text_bytes": path.stat().st_size,
                "text_sha256": sha256(path.read_bytes()),
                "source_payload_bytes": len(source_part),
                "source_payload_sha256": sha256(source_part),
                "round_trip_verified": True,
            }
        )

    manifest = {
        "source_file": args.capture.name,
        "source_bytes": len(source),
        "source_records": total_records,
        "source_sha256": sha256(source),
        "record_bytes": RECORD_BYTES,
        "hpe_record_marker": "CSI record:",
        "words_per_record": RECORD_BYTES // 4,
        "records_per_file": args.records_per_file,
        "parts": parts,
    }
    manifest_path = args.output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(
        f"Created {len(parts)} HPE text chunks for {total_records} records; "
        "all round trips verified"
    )
    print(manifest_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
