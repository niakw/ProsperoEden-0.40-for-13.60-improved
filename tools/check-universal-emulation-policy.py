#!/usr/bin/env python3
"""Regression guard: Encore emulation/runtime fixes apply to ALL titles.

A title's log can reproduce the bug, but no FC27/other ROM whitelist may be
used to enable correctness, memory safety, guest networking or FPS diagnostics.
"""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
def read(path: str) -> str: return (root / path).read_text()

main = read("headless/main.cpp")
graphics = read("headless/graphics.cpp")
policy = read("headless/encore_performance_policy.h")
hle = read("headless/backports/eden-fc27-hle-compat.patch")
offline = read("headless/backports/eden-ps5-guest-offline.patch")
domain_filter = read("headless/backports/eden-ps5-guest-domain-filter.patch")
services = read("headless/prosperoeden/eden_services.cpp")
lib = read("headless/prosperoeden/pe/ui/library.cpp")

# Real account and socket HLE improvements are registered in universal service
# dispatch tables; no title-id-gated workaround suppresses exceptions.
for s in ('{130, &ACC_U0::LoadOpenContext, "LoadOpenContext"}',
          '{19, &BSD_USA::Ioctl, "Ioctl"}'):
    assert s in hle, s
assert hle.count('+    write_buffer.resize(guest_addrin.len);') == 2
assert "kGuestNetworkOffline = true" in offline  # immutable legacy patch cache
assert "kGuestNetworkOffline = false" in domain_filter  # runtime overlay
assert "SocketImpl(Domain domain, Type type, Protocol protocol)" in offline
assert 'GetAddrInfoError::NODATA' in domain_filter
assert 'if (eden_network_host_blocked(host.c_str()))' in domain_filter
assert 'Settings::values.airplane_mode.SetValue(false);' in main

# The GPU/JIT defaults are global profile-level policies, never a single
# benchmark game's result hard-coded into the runtime.
for marker in ("performance_policy.async_shaders", "performance_policy.fast_gpu",
               "performance_policy.reactive_flushing", "Eden::JitList::enabled = false;",
               'Settings::values.vram_usage_mode.SetValue(Settings::VramUsageMode::Aggressive)'):
    assert marker in main, marker
for marker in ("frame_late_38", "frame_late_50", "frame_late_100",
               "EDEN_VULKAN_FRAME frames=%u", "frame_sample_count = 0;"):
    assert marker in graphics, marker
assert "compile_ahead" in policy
assert "kPolicies[EncoreOverrides::kAuthoredProfileCount]" in policy
assert "EDEN_VULKAN_FRAME" in graphics
assert "frame_late_38 += present_interval >= 0.038;" in graphics

# All installed games receive their complete Nlib image set. A one-title log
# must not affect launcher artwork or the emulated game's external connectivity.
assert 'const int wanted_screens = std::clamp(screen_count, 0, 3);' in services
assert "home_media_priority" not in services
assert "artwork_files.resize(6)" not in services
assert 'for (std::size_t offset = 0; offset < games_.size(); ++offset)' in lib

print("Universal HLE, guest networking, GPU/JIT and Nlib all-title policies: PASS")
