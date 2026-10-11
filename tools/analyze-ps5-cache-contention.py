#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only FC27 cache-contention / frame-pacing audit.

Sampled FPS is an average over several seconds, not a per-frame timing proof.
Only pair EDEN_FRAME_PRESSURE with an immediately preceding EDEN_VULKAN_FRAME
when the exact reported total frame matches; don't extrapolate to log-off runs.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from pathlib import Path
import re
import statistics

FIELDS = re.compile(r"\b([A-Za-z][A-Za-z_0-9]*)=(-?[0-9]+(?:\.[0-9]+)?)")

def values(line: str) -> dict[str, float]:
    return {key: float(value) for key, value in FIELDS.findall(line)}

def windows(lines: list[str]) -> list[dict[str, float]]:
    result = []
    pending = None
    for line in lines:
        if "EDEN_VULKAN_FRAME " in line:
            pending = values(line.partition("EDEN_VULKAN_FRAME ")[2])
        elif "EDEN_FRAME_PRESSURE " in line and pending is not None:
            pressure = values(line.partition("EDEN_FRAME_PRESSURE ")[2])
            if pending.get("total") is not None and pending["total"] == pressure.get("frame"):
                result.append({**pending, **pressure})
            pending = None
    return result

def med(rows: list[dict[str, float]], key: str) -> float | None:
    values_ = [r[key] for r in rows if key in r]
    return statistics.median(values_) if values_ else None

def report(rows: list[dict[str, float]]) -> str:
    if not rows:
        return "NO_VALID_WINDOWS (requires matching frame totals)"
    near30 = [r for r in rows if r.get("fps", 0) >= 29.9]
    slow = [r for r in rows if r.get("fps", 0) < 25]
    groups = [("near30", near30), ("slow_below25", slow)]
    out = [f"all_windows={len(rows)} near30={len(near30)} below25={len(slow)}"]
    for name, subset in groups:
        if not subset:
            continue
        def count(predicate): return sum(bool(predicate(r)) for r in subset)
        out.append(
            f"{name}: n={len(subset)} contended_median={med(subset, 'cache_contended')} "
            f"blocked_ms_median={med(subset, 'cache_wait_ms')} "
            f"cache_ge1000={count(lambda r: r.get('cache_contended', 0)>=1000)} "
            f"worst_over50={count(lambda r: r.get('worst_ms', 0)>50)} "
            f"late50_windows={count(lambda r: r.get('late50', 0)>0)} "
            f"max_worst_ms={max(r.get('worst_ms', 0) for r in subset):.3f}"
        )
    out.append("NOTE: try_lock failures are instrumented, not per-frame mutex latency; "
               "blocked_ms sums waits across guest threads. FPS near 30 is not smoothness.")
    return "\n".join(out)

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", type=Path, nargs="+")
    args = parser.parse_args()
    for path in args.logs:
        print(path)
        print(report(windows(path.read_text(encoding="utf-8", errors="replace").splitlines())))

if __name__ == "__main__":
    main()
