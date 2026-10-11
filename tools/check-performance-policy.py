#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Encore owns all seven ProsperoEden performance controls through its profile policy."""
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
policy = (root / "headless/encore_performance_policy.h").read_text()
main = (root / "headless/main.cpp").read_text()

fields = (
    "compile_ahead",
    "async_shaders",
    "fast_gpu",
    "unsafe_cpu",
    "unsafe_dma",
    "reactive_flushing",
    "skip_invalidation",
)
body = policy.split("struct Policy {", 1)[1].split("};", 1)[0]
for field in fields:
    assert re.search(rf"\bbool\s+{field}\s*;", body), field

# Every authored video tier has an explicit seven-switch policy.
rows = re.findall(r"\{false,\s*(?:true|false),\s*(?:true|false),\s*(?:true|false),\s*(?:true|false),\s*(?:true|false),\s*(?:true|false)\}", policy)
assert len(rows) == 4, rows
# Async shader compilation applies to ALL quality tiers, including Ultra.
# It may defer a new effect, but must not block the whole render pipeline.
assert all(re.search(r"\{false,\s*true,", row) for row in rows), rows
assert "There is no manual" not in policy  # policy is generic, not whitelist-driven

checks = (
    "performance_policy.compile_ahead",
    "performance_policy.async_shaders",
    "performance_policy.fast_gpu",
    "performance_policy.unsafe_cpu",
    "performance_policy.unsafe_dma",
    "performance_policy.reactive_flushing",
    "performance_policy.skip_invalidation",
)
for needle in checks:
    assert needle in main, needle

# One app process launches multiple games: accuracy state is reset before applying a new policy.
for reset in (
    "Settings::values.cpu_accuracy = Settings::CpuAccuracy::Auto;",
    "Settings::values.dma_accuracy.SetValue(Settings::DmaAccuracy::Default);",
    "Settings::values.use_reactive_flushing.SetValue(true);",
    "Settings::values.skip_cpu_inner_invalidation.SetValue(false);",
):
    assert reset in main, reset

# Shipping compile-ahead must not be promised when its required shared-JIT architecture is absent.
assert "#if EDEN_SHARED_JIT_AVAILABLE" in main
assert "Eden::JitList::enabled = false;" in main
assert "saved-block compile-ahead disabled" in main

# Custom visible settings derive a runtime tier instead of silently becoming the heavy profile.
assert "runtime_performance_profile" in main
assert "effective_resolution_for_tuning" in main
assert "effective_output_for_tuning" in main

# The development GPU timestamp recorder has a process-global query handle.
# On PS5 the Vulkan logical device is rebuilt for each game in one process.
# Never reuse old-device query pools or a prior title's failed/ring state.
vulkan_dev = (root / "headless/dev_vulkan.h").read_text()
generator = (root / "tools/prepare-vulkan-port.py").read_text()
assert "std::atomic<std::uint64_t> gpu_time_session{0};" in vulkan_dev
assert "Eden::DevVulkan::ResetForTitle();" in main
for token in ("disable_null_descriptor = false;", "disable_descriptor_buffer = false;",
              "robustness2 = false;", "disable_sparse = false;",
              "disable_multi_range = false;", "disable_custom_border = true;",
              "sync_submissions = false;", "gpu_time = false;",
              "disable_conditional_rendering = false;", "compute_barriers = true;",
              "hcr_mode = 1;"):
    assert token in vulkan_dev[vulkan_dev.index("inline void ResetForTitle()"):], token
# The 64-draw handoff is DEV ONLY; ordinary builds must retain 8 as
# performance.h's initial mask. The next title resets the experiment.
assert "inline std::atomic<unsigned> dispatch_mask{7};" in (root / "headless/performance.h").read_text()
for marker in ("graphics_usage_from_pool.store(true", "gc_keep_dirty.store(true",
               "dispatch_mask.store(63", "idle_spin_iterations.store(5000",
               "jit_duplicate_tracking.store(false", "pc_sample_core.store(0",
               "pc_fast.store(false", "capture_early.store(false",
               "firmware_applets.store(false", "trace_fs_callers.store(false"):
    assert marker in main, marker
assert "Eden::DevVulkan::gpu_time_session.fetch_add(1, std::memory_order_release);" in main
assert "const u64 session = ::Eden::DevVulkan::gpu_time_session.load(std::memory_order_acquire);" in generator
assert "gpu_time = GpuTimeProbe{};" in generator
assert generator.index("gpu_time = GpuTimeProbe{};") < generator.index("if (gpu_time.failed) return;")
assert "void GpuTimeDestroy(const Device& device)" in generator
assert "dld.vkDestroyQueryPool(handle, *gpu_time.pool, nullptr);" in generator
assert "worker_thread.request_stop();" in generator
assert "if (worker_thread.joinable()) worker_thread.join();" in generator
assert "GpuTimeDestroy(device);" in generator
assert "if (gpu_time.pool) GpuTimeDestroy(device);" in generator
assert generator.index("if (worker_thread.joinable()) worker_thread.join();") < generator.index("if (gpu_time.pool) GpuTimeDestroy(device);")
# One failed 100ms PS5 direct-memory query must not be treated as a
# confirmed low-memory event and trigger huge dirty texture downloads.
# Zero previous observations, or two consecutive misses, stay conservative.
perf = (root / "headless/performance.cpp").read_text()
assert "static std::atomic<unsigned> consecutive_failures{0};" in perf
assert "checked_ns.compare_exchange_strong(last, now, std::memory_order_acq_rel," in perf
assert "query_in_flight.exchange(true, std::memory_order_acq_rel)" in perf
assert "static std::int64_t cached_direct_total = 0;" in perf
assert "if (observed_total > 0) cached_direct_total = observed_total;" in perf
assert "sceKernelAvailableDirectMemorySize(0, cached_direct_total, 0x4000" in perf
assert "IsKernelFreeSpanValid(cached_direct_total, start, largest)" in perf
assert "IsKernelFreeSpanValid(total, start, observed)" in perf
assert "query_in_flight.store(false, std::memory_order_release);" in perf
assert "EDEN_PS5_DMEM_PROBE_SLOW latency_ns=%lld known=%u" in perf
assert "now <= last || now - last < 100'000'000" in perf
assert "static std::atomic<bool> has_valid_sample{false};" in perf
assert "if (!has_valid_sample.load(std::memory_order_acquire) || failed >= 2)" in perf
assert 'EDEN_PS5_DMEM_PROBE_FAILED consecutive=%u fallback=%s' in perf
assert "graphics_memory_short.store(largest < kShortMemory" in perf
# The query remains at the original 100-ms rate when headroom is unknown
# or constrained. The high-headroom-only slowdown runs AFTER the original
# per-frame fast return, without making more atomics hot at 60/120 FPS.
probe_policy = (root / "headless/direct_pool_probe_policy.h").read_text()
assert "kProbeFastNs = 100'000'000" in probe_policy
assert "kProbeHighHeadroomNs = 250'000'000" in probe_policy
assert "kProbeHighHeadroomBytes = 4ULL << 30" in probe_policy
assert "failed_queries == 0" in probe_policy
assert "has_valid_sample && failed_queries == 0" in probe_policy
refresh = perf.split("static void RefreshFreeMemory() {", 1)[1].split("static bool GraphicsMemoryShort()", 1)[0]
assert refresh.index("now <= last || now - last < 100'000'000") < refresh.index(
    "::Eden::DirectPool::ProbeIntervalNs(")
assert refresh.index("::Eden::DirectPool::ProbeIntervalNs(") < refresh.index(
    "checked_ns.compare_exchange_strong(")
# A new title starts with NO trusted previous-title memory sample. Reset only
# after the prior renderer has stopped, before the next game's first frame.
main_reset = main.index("Eden::Performance::ResetDirectMemoryProbeForTitle();")
assert main.index("Eden::Display::ResetSkipFrameTracking();") < main_reset
assert "void ResetDirectMemoryProbeForTitle() noexcept" in perf
reset = perf.split("void ResetDirectMemoryProbeForTitle() noexcept", 1)[1].split("static void RefreshFreeMemory()", 1)[0]
assert "if (query_in_flight.load(std::memory_order_acquire)) std::abort();" in reset
assert "has_valid_sample.store(false" in reset
assert "consecutive_failures.store(0" in reset
assert "largest_free_block.store(0" in reset
assert "graphics_memory_short.store(true" in reset
assert "checked_ns.store(0" in reset
assert "ResetDirectMemoryProbeForTitle() noexcept;" in (root / "headless/performance.h").read_text()
print("Encore automatic performance policy: 7/7 controls owned by 4 tiers + Custom derivation PASS")
print("GPU timing device lifecycle: explicit opt-in, per-title query reset contract PASS")
