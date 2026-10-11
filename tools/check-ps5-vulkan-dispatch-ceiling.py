#!/usr/bin/env python3
"""R309: compile the exact C++ Vulkan FlushWork replacement and exercise cadence.

The pinned Eden source used to test its 512-draw ceiling only on the mask's
next handoff: masks 7/63 flushed at draw 519/575, respectively. No stutter
or speed claim is derived from this host fixture.
"""
from __future__ import annotations

import ast
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
script = (ROOT / "tools/prepare-vulkan-port.py").read_text()
main = (ROOT / "headless/main.cpp").read_text()
perf = (ROOT / "headless/performance.h").read_text()
ast.parse(script)

replacements = []
for node in ast.walk(ast.parse(script)):
    if not isinstance(node, ast.Tuple) or len(node.elts) != 2:
        continue
    try:
        old = ast.literal_eval(node.elts[0])
        new = ast.literal_eval(node.elts[1])
    except (ValueError, TypeError, SyntaxError, KeyError):
        continue
    if isinstance(new, str) and "draw_counter >= DRAWS_TO_DISPATCH" in new:
        replacements.append((old, new))

assert len(replacements) == 1, "exactly one native hard-ceiling replacement"
old, new = replacements[0]
assert "if ((++draw_counter & CHECK_MASK) != CHECK_MASK)" in old
assert "if (draw_counter < DRAWS_TO_DISPATCH)" in old
assert new.index("draw_counter >= DRAWS_TO_DISPATCH") < new.index("draw_counter & CHECK_MASK")
assert "scheduler.Flush();" in new and "scheduler.DispatchWork();" in new
assert "draw_counter = 0;" in new
assert "static constexpr u32 DRAWS_TO_DISPATCH = 512;" in script
assert "inline std::atomic<unsigned> dispatch_mask{7};" in perf
assert "Eden::Performance::dispatch_mask.store(63, std::memory_order_relaxed);" in main
assert "Eden::Performance::dispatch_mask = static_cast<unsigned>(draws - 1);" in main
assert "draws >= 8 && draws <= 512 && (draws & (draws - 1)) == 0" in main

# Native C++ harness: use the exact generated function body, not a retyped Python model.
cpp = r"""
#include <cassert>
#include <cstdint>
#include <cstdio>
using u32 = std::uint32_t;
struct Scheduler {
    unsigned dispatches{};
    unsigned flushes{};
    void DispatchWork() { ++dispatches; }
    void Flush() { ++flushes; }
};
struct Device {
    Scheduler scheduler{};
    u32 draw_counter{};
    u32 mask{};
    void Step() {
        static constexpr u32 DRAWS_TO_DISPATCH = 512;
        const u32 CHECK_MASK = mask;
__EXACT_BODY__
    }
};
int main() {
    for (const u32 batch : {8u, 16u, 32u, 64u, 128u, 256u, 512u}) {
        Device device{{}, 0u, batch - 1};
        for (u32 i = 1; i <= 2048; ++i) {
            device.Step();
            assert(device.draw_counter < 512);
            assert(device.scheduler.flushes == i / 512);
            assert(device.scheduler.dispatches == (i / 512) * (512 / batch - 1)
                                                + (i % 512) / batch);
        }
        std::printf("PASS batch=%u flushes=%u dispatches=%u\n", batch,
                    device.scheduler.flushes, device.scheduler.dispatches);
    }
}
""".replace("__EXACT_BODY__", "\n".join("        " + line for line in new.splitlines()))
cpp = cpp.replace("#include <cstdio>", "#include <cstdio>\n#include <initializer_list>")
compiler = shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler, "host C++ compiler required for actual FlushWork fixture"
with tempfile.TemporaryDirectory(prefix="eden-r309-dispatch-") as d:
    source = Path(d) / "ceiling.cpp"
    output = Path(d) / "ceiling"
    source.write_text(cpp)
    subprocess.run([compiler, "-std=c++20", "-O2", "-Wall", "-Wextra",
                    "-Werror", str(source), "-o", str(output)], check=True)
    subprocess.run([str(output)], check=True)
print("PASS R309: native C++ source exact-replay draw ceiling, shipping and dev cadence contracts")
