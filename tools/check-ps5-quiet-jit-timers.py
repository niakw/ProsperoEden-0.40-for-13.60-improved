#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Verify exact PS5-generated JIT compile timer is *inactive* in quiet mode.

Developer/all-on builds previously read two steady clocks for every
guest A64 block, even with Detailed Logging disabled. This host test
compiles the actual CMake template to prove balanced live toggles and
zero quiet-mode clock sampling (default-constructed start clock).
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
cmake=(root/"headless/CMakeLists.txt").read_text()
start=cmake.index("        set(quiet_jit_timer [=[")
end=cmake.index("]=])",start)
snippet=cmake[start:end].split("[=[",1)[1]
assert "bool active;" in snippet
assert "active(eden_native_detailed_logging && eden_native_detailed_logging())" in snippet
assert "if (active) start = std::chrono::steady_clock::now();" in snippet
assert "if (active && eden_jit_compile)" in snippet
assert 'extern \\"C\\" bool eden_native_detailed_logging() noexcept __attribute__((weak));' in cmake
assert "if (eden_native_detailed_logging && eden_native_detailed_logging() && ++pressure_count <= 200)" in cmake
assert "std::chrono::steady_clock::time_point start = std::chrono::steady_clock::now()" not in cmake
assert 'string(REPLACE "${compile_site}" "${compile_site}${quiet_jit_timer}"' in cmake

program=r"""
#include <cassert>
#include <chrono>
#include <thread>
#include <cstdio>
static bool detailed=false;
static unsigned callbacks=0;
static unsigned long long elapsed=0;
extern "C" bool eden_native_detailed_logging() noexcept __attribute__((weak));
extern "C" void eden_jit_compile(unsigned, unsigned long long) __attribute__((weak));
extern "C" bool eden_native_detailed_logging() noexcept {return detailed;}
extern "C" void eden_jit_compile(unsigned core, unsigned long long ns) {
    assert(core==2);
    assert(ns>0);
    callbacks++;
    elapsed+=ns;
}
void compile_one() {
    struct {unsigned processor_id=2;} conf;
INJECT
    if (!detailed) {
        assert(!eden_compile_timer.active);
        assert(eden_compile_timer.start==std::chrono::steady_clock::time_point{});
    } else {
        assert(eden_compile_timer.active);
        assert(eden_compile_timer.start!=std::chrono::steady_clock::time_point{});
        std::this_thread::sleep_for(std::chrono::microseconds(5));
    }
}
int main() {
    for (int i=0;i<1000;++i) compile_one();
    assert(callbacks==0 && elapsed==0);
    detailed=true;
    compile_one();
    assert(callbacks==1 && elapsed>0);
    detailed=false;
    for (int i=0;i<1000;++i) compile_one();
    assert(callbacks==1);
    std::puts("PASS: zero JIT block clock samples/callbacks while quiet, exact one timed verbose sample");
}
""".replace("INJECT",snippet)
compiler=shutil.which("clang++-18") or shutil.which("clang++") or shutil.which("g++")
assert compiler
with tempfile.TemporaryDirectory(prefix="eden-jit-quiet-timer-") as tmp:
    p=Path(tmp)
    source=p/"timer.cpp"
    binary=p/"timer"
    source.write_text(program)
    subprocess.run([compiler,"-std=c++20","-O2","-Wall","-Wextra","-Werror",
                    str(source),"-o",str(binary)],check=True)
    subprocess.run([str(binary)],check=True,timeout=10)
