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
perf=(root/"headless/performance.h").read_text()
services=(root/"headless/prosperoeden/eden_services.cpp").read_text()
assert "if (detailed_gpu_profile.load(std::memory_order_relaxed))\n        counter.fetch_add(1, std::memory_order_relaxed);" in perf
assert "detailed_gpu_profile.store(value.detailed_logging" in services

assert 'string(REPLACE "${compile_site}" "${compile_site}${quiet_jit_timer}"' in cmake

program=r"""
#include <cassert>
#include <chrono>
#include <thread>
#include <cstdio>
static bool detailed=false;
static unsigned callbacks=0;
static unsigned long long elapsed=0;
#include <atomic>
static std::atomic<unsigned long long> memory_callback_counter{};
static std::atomic<bool> detailed_gpu_profile{false};
static void CountJit(std::atomic<unsigned long long>& counter) {
    if (detailed_gpu_profile.load(std::memory_order_relaxed))
        counter.fetch_add(1, std::memory_order_relaxed);
}
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
    for (int i=0;i<1000;++i) { compile_one(); CountJit(memory_callback_counter); }
    assert(callbacks==0 && elapsed==0 && memory_callback_counter.load()==0);
    detailed=true;
    detailed_gpu_profile.store(true);
    CountJit(memory_callback_counter);
    assert(memory_callback_counter.load()==1);
    compile_one();
    assert(callbacks==1 && elapsed>0);
    detailed=false;
    detailed_gpu_profile.store(false);
    for (int i=0;i<1000;++i) { compile_one(); CountJit(memory_callback_counter); }
    assert(memory_callback_counter.load()==1);
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


# R299: test the exact extracted shared-JIT dispatch-counter function in
# addition to the CMake timer. These counters are diagnostics, not guest state.
support=(root/"headless/dynarmic/jit_group_support.inc").read_text()
impl=(root/"headless/dynarmic/jit_impl.inc").read_text()
assert "if (!eden_native_detailed_logging || !eden_native_detailed_logging()) return;" in support
assert "const bool timed = eden_native_detailed_logging && eden_native_detailed_logging();" in impl
assert "const u64 start = timed ? EdenClockNs() : 0;" in impl
assert "const u64 translated = timed ? EdenClockNs() : 0;" in impl
assert "const u64 optimized = timed ? EdenClockNs() : 0;" in impl
assert "if (timed) EdenReportCompile(descriptor, start, translated, optimized);" in impl
assert "if (eden_native_detailed_logging && eden_native_detailed_logging() &&\n            ++pressure_count <= 200)" in impl
assert "if (report_clear) std::printf(\"EDEN_JIT_CLEAR_BEGIN" in impl
assert "if (report_clear) {" in impl
assert "const auto clear_started = report_clear ?" in impl
assert "std::chrono::steady_clock::now() - clear_started" in impl

fragment="enum EdenPath : unsigned" + support.split("enum EdenPath : unsigned",1)[1].split("std::mutex eden_groups_mutex;",1)[0]
counter_program=r"""
#include <array>
#include <atomic>
#include <cassert>
#include <cstdio>
using u32=unsigned;
static bool detailed=false;
extern "C" bool eden_native_detailed_logging() noexcept __attribute__((weak));
extern "C" bool eden_native_detailed_logging() noexcept { return detailed; }
namespace {
INJECT
}
int main() {
    for (int i=0; i<100000; ++i) {
        EdenCount(0,EdenRuns);
        EdenCount(1,EdenLookups);
    }
    assert(eden_path[0].values[EdenRuns].load()==0);
    assert(eden_path[1].values[EdenLookups].load()==0);
    detailed=true;
    EdenCount(0,EdenRuns);
    EdenCount(1,EdenLookups,7);
    assert(eden_path[0].values[EdenRuns].load()==1);
    assert(eden_path[1].values[EdenLookups].load()==7);
    detailed=false;
    EdenCount(0,EdenRuns);
    assert(eden_path[0].values[EdenRuns].load()==1);
    std::puts("PASS: real shared-JIT dispatch counters remain untouched in quiet mode and follow live toggle");
}
""".replace("INJECT",fragment)
with tempfile.TemporaryDirectory(prefix="eden-jit-quiet-dispatch-") as tmp:
    p=Path(tmp)
    source=p/"dispatch.cpp"
    binary=p/"dispatch"
    source.write_text(counter_program)
    subprocess.run([compiler,"-std=c++20","-O2","-Wall","-Wextra","-Werror",
                    str(source),"-o",str(binary)],check=True)
    subprocess.run([str(binary)],check=True,timeout=10)
