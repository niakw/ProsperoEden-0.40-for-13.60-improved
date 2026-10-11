#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""R306: audit the bounded Eden #4473 PS5-native Vulkan port contract.

No console, network or ROM required. Native CMake's exact-once source anchors
are separately enforced during PS5 configure. This checks integration and
models GPU-owned dirty-range subtraction incl. split and empty intersections.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
port = (ROOT / "headless/eden-buffer-4473.cmake").read_text()
cmake = (ROOT / "headless/CMakeLists.txt").read_text()

assert 'if(PS5_NATIVE AND EDEN_PS5_VULKAN)' in cmake
assert 'include("${EDEN_PORT_DIR}/eden-buffer-4473.cmake")' in cmake
assert "if(NOT PS5_NATIVE OR NOT EDEN_PS5_VULKAN)" in port
assert "source mismatch" in port
assert 'video_core/buffer_cache/buffer_cache.h' in port
assert "void BufferCache<P>::WriteMemory(DAddr device_addr, u64 size)" in port
assert "if (IsRegionGpuModified(device_addr, size))" in port
assert "gpu_modified_ranges.ForEachInRange(device_addr_out, range_size" in port
assert "add_upload(upload_start, gpu_start)" in port
assert "add_upload(upload_start, device_addr_out + range_size)" in port
assert "ClearDownload(device_addr, size);" in port
assert "std::min<size_t>(dma_state.method_count, header.size)" in port
assert "const bool kepler_payload" in port
assert "const bool macro_payload" in port
assert "upload_dirty = current_dirty;" in port
assert "current_dirty = false;" in port
assert "data.was_dirty || source_dirty" in port
assert 'target_include_directories(video_core BEFORE PRIVATE' in port
assert 'if("${PORT_BUILD_DIR}/dma_pusher.cpp" IN_LIST video_sources)' in port
assert 'file(READ "${eden4473_dma_input}" eden4473_dma)' in port
assert 'list(REMOVE_ITEM video_sources "${PORT_BUILD_DIR}/dma_pusher.cpp" dma_pusher.cpp)' in port

def upload_cpu_only(start: int, size: int, gpu_modified: list[tuple[int, int]]
                    ) -> list[tuple[int, int]]:
    """Model upstream #4473: upload only CPU regions not still GPU-owned."""
    end = start + size
    cursor = start
    copies = []
    for dirty_start, dirty_end in sorted(gpu_modified):
        left, right = max(dirty_start, start), min(dirty_end, end)
        if left >= right:
            continue
        assert cursor <= left, "test fixtures require nonoverlapping dirty ranges"
        if left > cursor:
            copies.append((cursor, left))
        cursor = right
    if cursor < end:
        copies.append((cursor, end))
    return copies

assert upload_cpu_only(100, 100, []) == [(100, 200)]
assert upload_cpu_only(100, 100, [(120, 180)]) == [(100, 120), (180, 200)]
assert upload_cpu_only(100, 100, [(100, 200)]) == []
assert upload_cpu_only(100, 100, [(80, 110), (180, 250)]) == [(110, 180)]
assert upload_cpu_only(100, 100, [(80, 99), (201, 250)]) == [(100, 200)]
assert upload_cpu_only(100, 100, [(101, 130), (140, 159), (160, 175)]) == [
    (100, 101), (130, 140), (159, 160), (175, 200)]
# #4473 must not alter the global video frontend, controller layouts or
# JIT/executable memory; the additional implementation is Vulkan-only.
for forbidden in ("eglMakeCurrent", "GX2", "controller_semantic", "JitAllocator",
                  "mutex.unlock()", "VK_ERROR_DEVICE_LOST"):
    assert forbidden not in port
print("PASS R306: bounded Eden #4473 PS5 Vulkan cache/Kepler source overlay and range semantics")
print("NOTE: source/range correctness is not a claim of improved FC27 frame pacing")
