#!/usr/bin/env python3
"""Read-only Encore network-accepted.log analyzer (launcher, guest, native).

Never reconfigures DNS; never performs network lookups. Counts successful API
calls/bytes, not on-the-wire packets, and does not infer IP->domain ownership.

Usage:
  python3 tools/analyze-ps5-network-audit.py logs/network-accepted.log*
  python3 tools/analyze-ps5-network-audit.py --self-test
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path
import re
import sys
import tempfile

LINE = re.compile(
    r"^epoch=(\d+) scope=(launcher|guest|native) "
    r"event=([a-z][a-z-]*) target=(\S{1,256}) "
    r"bytes=(\d+) status=(-?\d+)$"
)
IPV4_PORT = re.compile(
    r"^(?:\d{1,3}\.){3}\d{1,3}:\d{1,5}$"
)
DNS_EVENTS = {"dns-allowed", "dns-denied", "dns-resolved", "dns-error"}
SOCKET_EVENTS = {"connect", "tx", "rx", "numeric-ip"}


def summarize(paths: list[Path]) -> dict:
    by_event: Counter[tuple[str, str]] = Counter()
    dns: dict[str, Counter[str]] = defaultdict(Counter)
    connections: Counter[tuple[str, str]] = Counter()
    io: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    malformed = 0
    observed = 0
    latest_epoch = None
    earliest_epoch = None
    for path in paths:
        with path.open(encoding="utf-8", errors="replace") as f:
            for row in f:
                match = LINE.fullmatch(row.rstrip("\r\n"))
                if not match:
                    malformed += 1
                    continue
                epoch, scope, event, target, num_bytes, status = match.groups()
                timestamp = int(epoch)
                earliest_epoch = timestamp if earliest_epoch is None else min(earliest_epoch, timestamp)
                latest_epoch = timestamp if latest_epoch is None else max(latest_epoch, timestamp)
                observed += 1
                by_event[(scope, event)] += 1
                if event in DNS_EVENTS:
                    dns[event][target.lower().rstrip(".")] += 1
                elif event in SOCKET_EVENTS:
                    if event == "connect":
                        connections[(scope, target)] += 1
                    if event in ("tx", "rx"):
                        io[(scope, target)][event] += int(num_bytes)
                        io[(scope, target)][event + "_calls"] += 1
    return {
        "events": observed,
        "invalid_lines": malformed,
        "start": earliest_epoch,
        "end": latest_epoch,
        "by_event": by_event,
        "dns": dns,
        "connect": connections,
        "io": io,
    }


def display(report: dict, top: int) -> str:
    lines = [
        f"Events: {report['events']:,}; malformed lines: {report['invalid_lines']:,}; "
        f"epoch interval: {report['start']}–{report['end']}",
        "",
        "Events by layer (guest HLE and native socket calls can refer to the SAME traffic):",
    ]
    for (scope, event), count in report["by_event"].most_common():
        lines.append(f"  {scope:8} {event:16} {count:>9,}")
    for kind, label in (
        ("dns-denied", "Locally denied domain lookups"),
        ("dns-allowed", "Guest domains not denied by Eden (NOT proof of DNS success)"),
        ("dns-resolved", "Native launcher DNS resolution success"),
        ("dns-error", "Native launcher DNS resolution failure"),
    ):
        lines.extend(("", label + ":"))
        ranking = report["dns"][kind].most_common(top)
        lines.extend(f"  {count:>7,}  {host}" for host, count in ranking)
        if not ranking:
            lines.append("  (none observed)")
    lines.extend(("", "Socket connects observed by Eden's API boundaries:"))
    for (scope, target), count in report["connect"].most_common(top):
        lines.append(f"  {count:>7,}  {scope:8} {target}")
    if not report["connect"]:
        lines.append("  (none observed)")
    lines.extend(("", "Socket API bytes (not wire packets, duplicate layers possible):"))
    ranking = sorted(
        report["io"].items(),
        key=lambda item: item[1]["tx"] + item[1]["rx"],
        reverse=True,
    )[:top]
    for (scope, target), values in ranking:
        lines.append(
            f"  {scope:8} {target:32} "
            f"tx={values['tx']:,} ({values['tx_calls']} calls) "
            f"rx={values['rx']:,} ({values['rx_calls']} calls)"
        )
    if not ranking:
        lines.append("  (none observed)")
    direct = [
        (scope, host, count)
        for (scope, host), count in report["connect"].items()
        if IPV4_PORT.fullmatch(host)
    ]
    if direct:
        lines.extend(("", "Direct-IP destinations (cannot infer operator or bypass from IP alone):"))
        for scope, host, count in sorted(direct, key=lambda x: -x[2])[:top]:
            lines.append(f"  {count:>7,}  {scope:8} {host}")
    lines.extend((
        "",
        "NOTE: Eden domain matches precede ordinary DNS. NanoDNS/router DNS may",
        "still block an Eden-allowed lookup. DNS permission is not Internet access.",
        "NOTE: The logger observes selected API boundaries, not every PS5 packet.",
        "No domains are inferred from socket IPs; external DNS logs are needed",
        "to establish whether a direct-IP destination belongs to a publisher.",
    ))
    return "\n".join(lines)


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="eden-network-audit-report-") as tmp:
        path = Path(tmp) / "network-accepted.log"
        path.write_text("\n".join((
            "epoch=10 scope=guest event=dns-allowed target=allowed.example bytes=0 status=0",
            "epoch=11 scope=guest event=dns-denied target=API.EA.COM bytes=0 status=1",
            "epoch=12 scope=launcher event=dns-resolved target=api.nlib.cc bytes=0 status=0",
            "epoch=13 scope=guest event=connect target=203.0.113.10:443 bytes=0 status=0",
            "epoch=14 scope=guest event=tx target=fd:12 bytes=500 status=0",
            "epoch=15 scope=native event=tx target=203.0.113.10:443 bytes=500 status=0",
            "epoch=16 scope=guest event=rx target=fd:12 bytes=20 status=0",
            "not-a-valid-row",
        )) + "\n")
        report = summarize([path])
        assert report["events"] == 7 and report["invalid_lines"] == 1
        assert report["dns"]["dns-denied"]["api.ea.com"] == 1
        assert report["dns"]["dns-allowed"]["allowed.example"] == 1
        assert report["io"][("guest", "fd:12")]["tx"] == 500
        assert report["io"][("native", "203.0.113.10:443")]["tx"] == 500
        assert "duplicate layers possible" in display(report, 10)
        assert "Eden-allowed lookup" in display(report, 10)
    print("NETWORK_AUDIT_ANALYSIS_PASS")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", type=Path, nargs="*",
                        help="network-accepted.log or network-accepted.log.prev")
    parser.add_argument("--top", type=int, default=25)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if not args.logs:
        parser.error("provide at least one network-accepted.log file")
    if not 1 <= args.top <= 100:
        parser.error("--top must be between 1 and 100")
    for log in args.logs:
        if not log.is_file():
            parser.error(f"not a file: {log}")
    print(display(summarize(args.logs), args.top))
    return 0


if __name__ == "__main__":
    sys.exit(main())
