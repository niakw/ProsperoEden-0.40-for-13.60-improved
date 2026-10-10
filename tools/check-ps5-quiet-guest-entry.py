#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""R301: execute the actual PS5-generated A32/A64 Dynarmic Run wrapper.

In quiet mode the wrapper must not evaluate GetPC/GetFpcr/Regs/Fpscr or
GetSvcNumber just to call a profiler which would immediately return.
The guest Run, CPU phase transitions and result translation must remain.
This is a C++20 host mock, NOT PS5 firmware or gameplay qualification.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
cmake = (root / "headless/CMakeLists.txt").read_text()
anchor = 'string(REPLACE "    return TranslateHaltReason(m_jit->Run());"'
assert cmake.count(anchor) == 1
injection = cmake.split(anchor, 1)[1].split('wrapper "${wrapper}")', 1)[0]
# CMake quoted string is the replacement body; verify no unexpected quotes.
assert injection.count('"') == 2
escaped = injection.split('"')[1]
assert escaped.count(r"\n") >= 6
assert escaped.count("::Eden::Performance::SampleCpu(") == 2
assert escaped.count("if (eden_detailed_cpu_sample) ::Eden::Performance::SampleCpu") == 2
assert escaped.count("m_jit->Run()") == 1
assert escaped.count("cpu_state[m_core_index].phase.store(") == 2
assert escaped.count("return TranslateHaltReason(halt);") == 1
assert "detailed_gpu_profile.load(std::memory_order_relaxed)" in escaped

body = escaped.replace(r"\n", "\n")
def generated(bits: int) -> str:
    if bits == 64:
        pc, fp = "m_jit->GetPC()", "m_jit->GetFpcr()"
    else:
        pc, fp = "m_jit->Regs()[15]", "m_jit->Fpscr()"
    return body.replace("${sample_pc}", pc).replace("${sample_fp}", fp)

host = r"""
#include <array>
#include <atomic>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstdio>
namespace Eden::Performance {
enum class CpuPhase : unsigned { Kernel, Guest, Idle };
struct State { std::atomic<CpuPhase> phase{CpuPhase::Kernel}; };
std::array<State, 4> cpu_state{};
std::atomic<bool> detailed_gpu_profile{false};
std::atomic<unsigned> samples{0};
void SampleCpu(std::size_t, unsigned long long, unsigned long long,
               unsigned, unsigned) { ++samples; }
}
struct Jit {
    int run_calls=0, guest_phase_observed=0;
    int get_pc=0, get_fpcr=0, regs_calls=0, fpscr_calls=0;
    std::array<unsigned long long,16> registers{};
    int Run() {
        ++run_calls;
        if (Eden::Performance::cpu_state[0].phase.load() ==
            Eden::Performance::CpuPhase::Guest) ++guest_phase_observed;
        return 77;
    }
    unsigned long long GetPC() { ++get_pc; return 0x123456; }
    unsigned GetFpcr() { ++get_fpcr; return 0; }
    std::array<unsigned long long,16>& Regs() { ++regs_calls; return registers; }
    unsigned Fpscr() { ++fpscr_calls; return 0; }
};
struct Fixture {
    Jit jit{};
    Jit* m_jit=&jit;
    std::size_t m_core_index=0;
    unsigned svc_calls=0;
    unsigned GetSvcNumber() { ++svc_calls; return 11; }
    int TranslateHaltReason(int value) { return value; }
    int Run64() {
A64_CODE
    }
    int Run32() {
A32_CODE
    }
};
int main() {
    Fixture fixture;
    for (int i=0; i<20000; ++i) {
        assert(fixture.Run64()==77);
        assert(fixture.Run32()==77);
    }
    assert(fixture.jit.run_calls == 40000);
    assert(fixture.jit.guest_phase_observed == 40000);
    assert(fixture.jit.get_pc == 0 && fixture.jit.get_fpcr == 0);
    assert(fixture.jit.regs_calls == 0 && fixture.jit.fpscr_calls == 0);
    assert(fixture.svc_calls == 0 && Eden::Performance::samples == 0);
    assert(Eden::Performance::cpu_state[0].phase.load() ==
           Eden::Performance::CpuPhase::Kernel);
    Eden::Performance::detailed_gpu_profile.store(true);
    assert(fixture.Run64()==77 && fixture.Run32()==77);
    assert(fixture.jit.get_pc == 2 && fixture.jit.get_fpcr == 2);
    assert(fixture.jit.regs_calls == 2 && fixture.jit.fpscr_calls == 2);
    assert(fixture.svc_calls == 4 && Eden::Performance::samples == 4);
    Eden::Performance::detailed_gpu_profile.store(false);
    assert(fixture.Run64()==77 && fixture.Run32()==77);
    assert(fixture.jit.get_pc == 2 && fixture.jit.get_fpcr == 2);
    assert(fixture.jit.regs_calls == 2 && fixture.jit.fpscr_calls == 2);
    assert(fixture.svc_calls == 4 && Eden::Performance::samples == 4);
    assert(fixture.jit.run_calls == 40004);
    assert(fixture.jit.guest_phase_observed == 40004);
    std::puts("PASS: real A32/A64 Run wrappers skip quiet register sampling and preserve phases/results");
}
""".replace("A64_CODE", generated(64)).replace("A32_CODE", generated(32))

compiler = next((name for name in ("clang++-18","clang++","g++") if shutil.which(name)), None)
assert compiler, "C++20 compiler required"
with tempfile.TemporaryDirectory(prefix="eden-guest-entry-") as directory:
    source = Path(directory) / "guest_entry.cpp"
    binary = Path(directory) / "guest_entry"
    source.write_text(host)
    subprocess.run([compiler, "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
                    "-pthread", str(source), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True, timeout=15)
print("HOST ONLY: no PS5 native SDK, FW13.60 runtime or FPS measured.")
