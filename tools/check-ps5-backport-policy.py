#!/usr/bin/env python3
"""Prevent exploratory kernel/JIT backports from silently entering shipping builds."""
from pathlib import Path
root = Path(__file__).resolve().parents[1]
script = (root / "tools/apply-eden-backports.sh").read_text()
for flag, patch in (
    ("EDEN_EXPERIMENTAL_DUMMY_THREAD_WAITS", "eden-dummy-thread-waits.patch"),
    ("EDEN_EXPERIMENTAL_ICACHE_COHERENCE", "eden-dynarmic-icache-coherence.patch"),
    ("EDEN_EXPERIMENTAL_SM_HOST_WAIT", "eden-sm-host-wait.patch"),
):
    condition = "if [[ ${" + flag + ":-OFF} == ON ]]; then"
    start = script.index(condition)
    end = script.index("\nfi", start)
    assert patch in script[start:end], (flag, patch)
    assert script.count('apply_one "$root/headless/backports/' + patch + '"') == 1
    assert ":-OFF" in condition

# The Citron-inspired SM fix compiles, but is not automatically hardware-qualified.
assert 'validate_sm_host_wait' in script
# R307: the #4473/#4477 cache/fence fixes are already in the pinned
# backport replay. Do not stage a second derived buffer-cache header or
# duplicate Kepler/DMA implementation in the native Vulkan build.
native_cmake = (root / "headless/CMakeLists.txt").read_text()
gpu_patch = root / "headless/backports/eden-4473-4477.patch"
assert gpu_patch.is_file() and "gpu_modified_ranges.ForEachInRange" in gpu_patch.read_text()
assert script.count('apply_one "$root/headless/backports/eden-4473-4477.patch"') == 1
assert (root / "headless/eden-buffer-4473.cmake").exists() is False
assert "eden-buffer-4473.cmake" not in native_cmake
assert "eden4473/dma_pusher.cpp" not in native_cmake
assert "Eden #4473/#4477 are already applied once" in native_cmake
print("PASS R307: one authoritative audited Eden #4473/#4477 patch, no double Vulkan overlay")
print("PS5 experimental HLE/JIT/SM backports remain OFF by default: PASS")
