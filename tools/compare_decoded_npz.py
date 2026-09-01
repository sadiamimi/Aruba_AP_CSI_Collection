#!/usr/bin/env python3
"""Compare locally decoded CSI with HPE-parser CSI at selected raw records."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("local_npz", type=Path, help="local decoder NPZ")
    parser.add_argument("hpe_npz", type=Path, help="HPE JSON-converted NPZ")
    parser.add_argument(
        "--source-record-indices",
        type=int,
        nargs="+",
        help="raw record represented by each HPE record, in HPE record order",
    )
    parser.add_argument("--output-json", type=Path, help="optional comparison report")
    parser.add_argument(
        "--atol",
        type=float,
        default=0.0,
        help="absolute I/Q tolerance; default requires an exact match",
    )
    args = parser.parse_args()

    with np.load(args.local_npz) as local, np.load(args.hpe_npz) as hpe:
        local_source = np.asarray(
            local.get("source_record_index", np.arange(local["csi"].shape[0]))
        )
        hpe_count = hpe["csi"].shape[0]

        if args.source_record_indices is not None:
            wanted = np.asarray(args.source_record_indices, dtype=local_source.dtype)
            if wanted.size != hpe_count:
                raise SystemExit(
                    f"received {wanted.size} source indices for {hpe_count} HPE records"
                )
            local_positions = []
            for source_index in wanted:
                matches = np.flatnonzero(local_source == source_index)
                if matches.size == 0:
                    raise SystemExit(
                        f"raw record {int(source_index)} was not retained locally"
                    )
                local_positions.append(int(matches[0]))
            local_positions = np.asarray(local_positions)
        elif hpe_count == local["csi"].shape[0]:
            wanted = local_source
            local_positions = np.arange(hpe_count)
        else:
            raise SystemExit(
                "record counts differ; supply --source-record-indices for the HPE records"
            )

        local_csi = local["csi"][local_positions]
        hpe_csi = hpe["csi"]
        if local_csi.shape != hpe_csi.shape:
            raise SystemExit(
                f"CSI shape mismatch: local {local_csi.shape}, HPE {hpe_csi.shape}"
            )

        absolute_error = np.abs(local_csi - hpe_csi)
        mismatch_mask = absolute_error > args.atol
        metadata_equal: dict[str, bool] = {}
        for key in (
            "tone_index",
            "report_timestamp_us",
            "client_mac",
            "bssid",
            "rssi_dbm",
        ):
            if key not in local or key not in hpe:
                continue
            local_value = local[key]
            if key != "tone_index":
                local_value = local_value[local_positions]
            metadata_equal[key] = bool(np.array_equal(local_value, hpe[key]))

        report = {
            "local_npz": args.local_npz.name,
            "hpe_npz": args.hpe_npz.name,
            "source_record_indices": [int(value) for value in wanted],
            "local_decoded_positions": [int(value) for value in local_positions],
            "csi_shape": list(local_csi.shape),
            "complex_samples_compared": int(absolute_error.size),
            "absolute_tolerance": args.atol,
            "iq_mismatches": int(np.count_nonzero(mismatch_mask)),
            "maximum_absolute_error": float(absolute_error.max(initial=0)),
            "metadata_equal": metadata_equal,
        }

    print(json.dumps(report, indent=2))
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(report, indent=2) + "\n")
    if report["iq_mismatches"] or not all(metadata_equal.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
