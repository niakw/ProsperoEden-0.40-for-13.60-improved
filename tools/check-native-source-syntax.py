#!/usr/bin/env python3
"""Fail early on native PS5 compilation errors without producing an application.

Reads the CMake compile database generated for the *current* tree and executes
Clang -fsyntax-only -Werror using each translation unit's real PS5 flags.
This is source validation, not a linker/package/hardware test.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
TARGETS = (
    "headless/ps5_net_compat.c",
    "headless/network_domain_rules.c",
    "headless/main.cpp",
    "headless/performance.cpp",
    "headless/prosperoeden/eden_services.cpp",
    "headless/prosperoeden/pe/ui/home.cpp",
    "headless/prosperoeden/pe/ui/library.cpp",
    "headless/prosperoeden/pe/ui/launcher.cpp",
    "headless/prosperoeden/pe/ui/settings.cpp",
)
# CMake derives these translation units from pinned Eden sources. Compile them
# before Ninja to reject cross-type shader IR and Fermi2D ABI errors early.
GENERATED_TARGETS = (
    "headless/maxwell_prmt_observed.cpp",
    "headless/fermi_2d_observed.cpp",
    "headless/sw_blitter_sized.cpp",
)

def syntax_check_flags(argv: list[str], generated: bool) -> list[str]:
    """Check with the actual target's warning policy, minus invalid Clang flags."""
    result = [flag for flag in argv if flag != "-Wno-error-all"]
    result += ["-fsyntax-only", "-ferror-limit=8"]
    if not generated:
        result.append("-Werror")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("native_build_dir", type=Path)
    parser.add_argument("--allow-stale", action="store_true",
                        help="Local audit only: override cached source paths; never use for release CI")
    args = parser.parse_args()
    db = args.native_build_dir.resolve() / "compile_commands.json"
    if not db.is_file():
        parser.error(f"native CMake compile database missing: {db}")
    records = json.loads(db.read_text())
    failures = []
    for relative in (*TARGETS, *GENERATED_TARGETS):
        source = (args.native_build_dir.resolve() if relative in GENERATED_TARGETS else ROOT) / relative
        entries = [row for row in records if Path(row["file"]).as_posix().endswith("/" + relative)]
        if not entries and args.allow_stale and relative.endswith(".c"):
            # Older cached CMake configuration predates the newly added native C unit.
            entries = [row for row in records if row["file"].endswith("/src/aligned_alloc.c")]
        if len(entries) != 1:
            failures.append(f"{relative}: expected one native compile command, got {len(entries)}")
            continue
        entry = entries[0]
        old = Path(entry["file"])
        if not args.allow_stale and old.resolve() != source.resolve():
            failures.append(f"{relative}: stale build command points at {old}")
            continue
        argv = list(entry["arguments"]) if "arguments" in entry else shlex.split(entry["command"])
        if "-c" not in argv or "-o" not in argv:
            failures.append(f"{relative}: expected compile-only CMake command")
            continue
        argv.pop(argv.index("-c"))
        pos = argv.index("-o")
        del argv[pos:pos + 2]
        # Last non-flag source argument in the original command is replaced with
        # the current fork path (even when using a deliberately stale local DB).
        previous = str(entry["file"])
        try:
            pos = argv.index(previous)
        except ValueError:
            failures.append(f"{relative}: source missing from compiler command")
            continue
        argv[pos] = str(source)
        if args.allow_stale:
            argv[1:1] = ["-I" + str(ROOT / "headless/prosperoeden"),
                         "-I" + str(ROOT / "headless"),
                         "-I" + str(ROOT / "src")]
        # The pinned Eden CMake flags contain "-Wno-error-all", which Clang 18
        # does not recognize. Ninja tolerates that diagnostic, but this
        # standalone preflight deliberately adds -Werror and would fail before
        # checking any generated GPU code. Drop only that unsupported flag.
        # Match real native warning severity: generated shader/Fermi objects
        # compile without -Werror, unlike the fork-owned launcher objects.
        argv = syntax_check_flags(argv, generated=relative in GENERATED_TARGETS)
        try:
            check = subprocess.run(argv, cwd=entry["directory"], text=True,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
        except (OSError, subprocess.TimeoutExpired) as exc:
            failures.append(f"{relative}: {exc}")
            continue
        if check.returncode:
            failures.append(f"{relative}:\n{check.stderr[:3500]}")
        else:
            print(f"PS5 syntax PASS: {relative}", flush=True)
    if failures:
        print("\n".join(failures), file=sys.stderr, flush=True)
        return 1
    print(f"PS5 native syntax preflight PASS ({len(TARGETS) + len(GENERATED_TARGETS)} translation units; no app build)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
