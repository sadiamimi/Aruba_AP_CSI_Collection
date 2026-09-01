#!/usr/bin/env python3
"""Check HPE native csimond text framing and record-header timing."""

from __future__ import annotations

import argparse
import json
import re
import struct
from pathlib import Path


MARKER_RE = re.compile(r"^CSI record:\r?$", re.MULTILINE)
WORD_RE = re.compile(r"0x([0-9a-fA-F]{8})")
EXPECTED_DISPLAY_WORDS = 512
TIMESTAMP_MODULUS = 1 << 32


def mac_string(raw: bytes) -> str:
    return ":".join(f"{value:02x}" for value in raw)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Check record markers, displayed word counts, header identities, "
            "and timestamp rate in HPE native csimond text."
        )
    )
    parser.add_argument("capture", type=Path)
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args()

    text = args.capture.read_text(encoding="ascii", errors="replace")
    matches = list(MARKER_RE.finditer(text))
    records: list[dict[str, object]] = []

    for index, marker in enumerate(matches):
        start = marker.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        words = [int(value, 16) for value in WORD_RE.findall(text[start:end])]
        record: dict[str, object] = {
            "record_index": index,
            "displayed_words": len(words),
            "displayed_bytes": len(words) * 4,
            "complete_2048_byte_display": len(words) == EXPECTED_DISPLAY_WORDS,
        }

        if len(words) >= 7:
            header = b"".join(struct.pack("<I", word) for word in words[:7])
            record.update(
                {
                    "format_id": struct.unpack_from("<I", header, 0)[0],
                    "client_mac": mac_string(header[4:10]),
                    "bssid": mac_string(header[10:16]),
                    "chanspec": f"0x{struct.unpack_from('<H', header, 16)[0]:04x}",
                    "tx_streams": header[18],
                    "rx_streams": header[19],
                    "report_timestamp_us": struct.unpack_from("<I", header, 20)[0],
                    "association_timestamp_us": struct.unpack_from("<I", header, 24)[0],
                }
            )
        records.append(record)

    timestamps = [
        int(record["report_timestamp_us"])
        for record in records
        if "report_timestamp_us" in record
    ]
    intervals_us = [
        (current - previous) % TIMESTAMP_MODULUS
        for previous, current in zip(timestamps, timestamps[1:])
    ]
    timestamp_span_us = sum(intervals_us)
    achieved_rate_hz = (
        (len(timestamps) - 1) * 1_000_000 / timestamp_span_us
        if len(timestamps) > 1 and timestamp_span_us
        else None
    )

    clients = sorted(
        {str(record["client_mac"]) for record in records if "client_mac" in record}
    )
    bssids = sorted(
        {str(record["bssid"]) for record in records if "bssid" in record}
    )
    word_counts = [int(record["displayed_words"]) for record in records]

    report = {
        "source_file": args.capture.name,
        "source_bytes": args.capture.stat().st_size,
        "record_markers": len(records),
        "complete_2048_byte_displays": sum(
            bool(record["complete_2048_byte_display"]) for record in records
        ),
        "partial_displays": sum(
            not bool(record["complete_2048_byte_display"]) for record in records
        ),
        "displayed_word_count_min": min(word_counts) if word_counts else None,
        "displayed_word_count_max": max(word_counts) if word_counts else None,
        "clients": clients,
        "bssids": bssids,
        "timestamped_records": len(timestamps),
        "timestamp_span_us": timestamp_span_us,
        "achieved_rate_hz": achieved_rate_hz,
        "interval_ms_min": min(intervals_us) / 1000 if intervals_us else None,
        "interval_ms_mean": (
            sum(intervals_us) / len(intervals_us) / 1000 if intervals_us else None
        ),
        "interval_ms_max": max(intervals_us) / 1000 if intervals_us else None,
        "records": records,
    }

    print(f"source bytes: {report['source_bytes']}")
    print(f"CSI record markers: {report['record_markers']}")
    print(f"complete 2048-byte displays: {report['complete_2048_byte_displays']}")
    print(f"partial displays: {report['partial_displays']}")
    print(f"clients: {', '.join(clients) if clients else 'none'}")
    print(f"BSSIDs: {', '.join(bssids) if bssids else 'none'}")
    if achieved_rate_hz is not None:
        print(f"timestamp span: {timestamp_span_us / 1_000_000:.6f} s")
        print(f"achieved timestamp rate: {achieved_rate_hz:.6f} Hz")
        print(
            "timestamp intervals: "
            f"min={report['interval_ms_min']:.3f} ms, "
            f"mean={report['interval_ms_mean']:.3f} ms, "
            f"max={report['interval_ms_max']:.3f} ms"
        )

    if args.output_json:
        args.output_json.write_text(json.dumps(report, indent=2) + "\n")
        print(f"wrote: {args.output_json}")

    return 0 if records and timestamps else 1


if __name__ == "__main__":
    raise SystemExit(main())
