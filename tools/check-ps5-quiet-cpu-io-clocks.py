#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Verify R300 quiet CPU/IO clock gates in native generator (host only)."""
from pathlib import Path
import shutil, subprocess, tempfile

cmake = (Path(__file__).resolve().parents[1] / "headless/CMakeLists.txt").read_text()
def section(start, end):
    assert cmake.count(start) == 1, start
    return cmake.split(start, 1)[1].split(end, 1)[0]

idle = section('string(REPLACE "${idle_old}" [=[', ']=] physical_core_source').strip()
assert idle.startswith("void PhysicalCore::Idle() {")
assert "const bool profile_idle = ::Eden::Performance::detailed_gpu_profile.load(std::memory_order_relaxed);" in idle
assert "const long long start = profile_idle ? ::Eden::Performance::NowNs() : 0;" in idle
assert "if (profile_idle)\n            ::Eden::Performance::CountIdle(" in idle
assert "m_on_interrupt.wait(lk, [this] { return m_is_interrupted; });" in idle

for start, end, metric, name in [
    ('string(REPLACE "${ctrl_old}"', ' ctrl_source "${ctrl_source}")', "wait_start", "guest_sync_wait"),
    ('string(REPLACE "${producer_old}"', ' producer_source "${producer_source}")', "dequeue_start", "guest_dequeue_wait"),
    ('string(REPLACE "${ipc_old}"', ' ipc_source "${ipc_source}")', "ipc_start", "guest_ipc_wait"),
]:
    fragment = section(start, end)
    assert f"const auto {metric} = ::Eden::Performance::detailed_gpu_profile.load" in fragment
    assert f"if ({metric}) ::Eden::Performance::AddSince(::Eden::Performance::{name}, {metric});" in fragment
    assert fragment.index("::Eden::Performance::NowNs()") < fragment.index(f"if ({metric})")
fs_file = section('string(REPLACE "${fs_file_old}"', ' fs_file_source "${fs_file_source}")')
fs_storage = section('string(REPLACE "${fs_storage_old}"', ' fs_storage_source "${fs_storage_source}")')
for fragment, name in [(fs_file, "guest_fs_file"), (fs_storage, "guest_fs_storage")]:
    assert "const auto fs_start = ::Eden::Performance::detailed_gpu_profile.load" in fragment
    assert rf"if (fs_start) {{\n        ::Eden::Performance::AddSince(::Eden::Performance::{name}, fs_start);" in fragment
assert fs_file.index("backend->Read(") < fs_file.index("if (fs_start)") < fs_file.index("EDEN_FS_FILE_READ")
assert fs_storage.index("EDEN_FS_SHORT_STORAGE") < fs_storage.index("if (fs_start)")
assert "fs_read != static_cast<std::size_t>(length)" in fs_storage
fs_open = section('string(REPLACE "${call_old}"', ' fs_system_source "${fs_system_source}")')
assert r"if (::Eden::Performance::detailed_gpu_profile.load(std::memory_order_relaxed))\n        LOG_WARNING(Service_FS, \"EDEN_FS_OPEN" in fs_open
assert 'write_derived("${PORT_BUILD_DIR}/fs_i_filesystem.cpp" "#include \\"${EDEN_PORT_DIR}/performance.h\\"\\n${fs_system_source}")' in cmake

compiler = next((x for x in ("clang++-18", "clang++", "g++") if shutil.which(x)), None)
assert compiler, "C++20 compiler required"
program = r"""
#include <atomic>
#include <cassert>
#include <condition_variable>
#include <cstddef>
#include <cstdio>
#include <mutex>
namespace Eden::Performance {
std::atomic<bool> detailed_gpu_profile{false};
std::atomic<unsigned> idle_spin_iterations{0}, clock_reads{0}, counted{0};
long long NowNs() { return ++clock_reads; }
void CountIdle(std::size_t, long long, bool) { ++counted; }
}
class PhysicalCore {
public: void Idle();
private:
    std::mutex m_guard;
    std::condition_variable m_on_interrupt;
    bool m_is_interrupted{true};
    std::size_t m_core_index{0};
};
INJECT
int main() {
    PhysicalCore core;
    for (int i=0; i<10000; ++i) core.Idle();
    assert(Eden::Performance::clock_reads == 0 && Eden::Performance::counted == 0);
    Eden::Performance::detailed_gpu_profile.store(true);
    for (int i=0; i<5; ++i) core.Idle();
    assert(Eden::Performance::clock_reads == 10 && Eden::Performance::counted == 5);
    Eden::Performance::detailed_gpu_profile.store(false);
    for (int i=0; i<10000; ++i) core.Idle();
    assert(Eden::Performance::clock_reads == 10 && Eden::Performance::counted == 5);
    std::puts("PASS: extracted native Idle body skips quiet-mode clock probes and counters");
}
""".replace("INJECT", idle)
with tempfile.TemporaryDirectory(prefix="eden-quiet-cpuio-") as d:
    src, exe = Path(d)/"idle.cpp", Path(d)/"idle"
    src.write_text(program)
    subprocess.run([compiler, "-std=c++20", "-O2", "-pthread", "-Wall", "-Wextra",
                    "-Werror", str(src), "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True, timeout=10)
print("PASS: R300 native CMake CPU, IPC, sync, FS guards; short-read error always checked")
print("HOST-ONLY: native PS5 SDK and FC27/BOTW validation pending")
