#!/usr/bin/env python3
"""Split HPE native csimond text at CSI record boundaries."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


MARKERS = (b"CSI record:\n", b"CSI record:\r\n")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def find_markers(data: bytes) -> tuple[bytes, list[int]]:
    for marker in MARKERS:
        positions: list[int] = []
        offset = 0
        while True:
            position = data.find(marker, offset)
            if position < 0:
                break
            if position == 0 or data[position - 1 : position] == b"\n":
                positions.append(position)
            offset = position + len(marker)
        if positions:
            return marker, positions
    raise ValueError("No line-aligned 'CSI record:' markers were found")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Split HPE native csimond text into record-aligned files."
    )
    parser.add_argument("capture", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--records-per-file", type=int, default=100)
    args = parser.parse_args()

    if args.records_per_file <= 0:
        parser.error("--records-per-file must be positive")

    source = args.capture.read_bytes()
    marker, positions = find_markers(source)
    prefix = source[: positions[0]]
    blocks = [
        source[start : positions[index + 1] if index + 1 < len(positions) else len(source)]
        for index, start in enumerate(positions)
    ]

    args.output_dir.mkdir(parents=True, exist_ok=True)
    chunks: list[dict[str, object]] = []
    reconstructed = bytearray(prefix)

    for part_index, start_record in enumerate(
        range(0, len(blocks), args.records_per_file), start=1
    ):
        selected = blocks[start_record : start_record + args.records_per_file]
        end_record = start_record + len(selected) - 1
        chunk = prefix + b"".join(selected)
        filename = (
            f"{args.capture.stem}.part-{part_index:03d}."
            f"records-{start_record:06d}-{end_record:06d}{args.capture.suffix}"
        )
        output = args.output_dir / filename
        output.write_bytes(chunk)
        chunks.append(
            {
                "part": part_index,
                "filename": filename,
                "source_record_start": start_record,
                "source_record_end": end_record,
                "record_count": len(selected),
                "bytes": len(chunk),
                "sha256": sha256_bytes(chunk),
            }
        )
        reconstructed.extend(b"".join(selected))

    if bytes(reconstructed) != source:
        raise RuntimeError("Internal verification did not reconstruct the source")

    manifest = {
        "source_file": args.capture.name,
        "source_bytes": len(source),
        "source_sha256": sha256_bytes(source),
        "marker": marker.decode("ascii").rstrip("\r\n"),
        "source_record_count": len(blocks),
        "records_per_file": args.records_per_file,
        "prefix_bytes_repeated_in_each_chunk": len(prefix),
        "chunks": chunks,
        "verification": "chunk record blocks reconstruct the source byte-for-byte",
    }
    manifest_path = args.output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    print(f"source records: {len(blocks)}")
    for chunk in chunks:
        print(
            f"part {chunk['part']:03d}: records "
            f"{chunk['source_record_start']}-{chunk['source_record_end']} "
            f"({chunk['record_count']}), {chunk['bytes']} bytes"
        )
    print(f"wrote manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
