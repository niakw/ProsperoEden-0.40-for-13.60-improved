#!/usr/bin/env python3
"""Single domain-denylist wiring across guest DNS/NIFM and launcher resolver."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
guest = (root / "headless/backports/eden-ps5-guest-offline.patch").read_text()
domains = (root / "headless/backports/eden-ps5-guest-domain-filter.patch").read_text()
hosts = (root / "headless/network-hosts.txt").read_text()
resolver = (root / "headless/ps5_net_compat.c").read_text()
package = (root / "tools/package-headless-native.sh").read_text()
apply = (root / "tools/apply-eden-backports.sh").read_text()
main = (root / "headless/main.cpp").read_text()
http = (root / "headless/backports/eden-ps5-launcher-fast-http.patch").read_text()
services = (root / "headless/prosperoeden/eden_services.cpp").read_text()

assert "inline constexpr bool kGuestNetworkOffline = true;" in guest
assert "if (Eden::Encore::kGuestNetworkOffline) return {-1, Errno::NOTCONN};" in guest
assert guest.count("if (Eden::Encore::kGuestNetworkOffline) return {0, GetAddrInfoError::NODATA};") == 2
assert "enable == 0 || Eden::Encore::kGuestNetworkOffline" in guest
assert "const auto has_connection = !Eden::Encore::kGuestNetworkOffline" in guest
assert "eden-ps5-guest-offline.patch" in apply
assert "eden-ps5-guest-domain-filter.patch" in apply
assert '.encore-backport-guest-domain-filter.sha256' in apply
assert 'inline constexpr bool kGuestNetworkOffline = false;' in domains
assert domains.count('if (eden_network_host_blocked(host.c_str())) return {0, GetAddrInfoError::NODATA};') == 2
assert '#include "network_domain_rules.h"' in domains
assert "GetAddrInfoError::NODATA" in apply
assert "Settings::values.airplane_mode.SetValue(false);" in main
assert "Settings::values.airplane_mode.SetValue(true);" not in main
assert 'eden_network_filter_load(Eden::AppFile("network-hosts.txt").c_str())' in main
assert 'eden_network_host_blocked(node)' in resolver
assert 'eden_network_host_blocked(name)' in resolver
assert 'cp "$root/headless/network-hosts.txt" "$app/network-hosts.txt"' in package
assert 'nintendo.com' in hosts and 'ea.com' in hosts and 'gogcdn.net' in hosts

# Native HTTPS remains available to Home and guest networking is enabled.
assert 'Common::Net::MakeRequest("https://api.nlib.cc", endpoint)' in services
assert 'Common::Net::MakeRequest("https://api.nlib.cc", metadata_endpoint)' in services
assert 'const std::size_t timeout_seconds = url == "https://api.nlib.cc" ? 3 : 5;' in http
assert "std::unordered_map<std::string, std::chrono::steady_clock::time_point> next_retry;" in services
assert "std::lock_guard lock(retry_guard);" in services
# Current Nlib negative-result retry policy: 30 minutes for incomplete metadata,
# 5 minutes for transient network errors. The old six-hour policy was removed.
assert "std::chrono::minutes(30)" in services
assert "std::chrono::minutes(5)" in services
# Launcher Nlib remains separate from guest networking. The latest
# enrichment path supports cancelling pending jobs when Library changes or
# the application closes; do not require the obsolete 2-argument signature.
assert 'NlibEnrichment EnsureNlibEnrichment(std::uint64_t title_id, int language_choice,' in services
assert 'const std::atomic<bool>* cancel = nullptr)' in services
assert 'return cancel && cancel->load(std::memory_order_acquire);' in services
assert 'if (title_id == 0 || cancelled()) return {};' in services
assert 'EnsureNlibEnrichment(game.title_id, language_choice, cancel)' in services
assert 'const int wanted_screens = std::clamp(screen_count, 0, 3);' in services
assert 'std::vector<std::future<bool>> downloads;' in services
assert 'std::filesystem::last_write_time(' not in services
assert "std::filesystem::last_write_time(retry_marker" not in services

# UI cannot render the app's brand in place of missing game media.
widgets = (root / "headless/prosperoeden/pe/ui/widgets.cpp").read_text()
textures = (root / "headless/prosperoeden/pe/ui/textures.cpp").read_text()
assert "if (image.missing && c.textures.brand() != 0)" not in widgets
assert 'it->second.age >= retry_after' in textures
assert 'retry_after = it->second.failed_loads <= 1 ? 0.45f' in textures
print("Shared host+guest DNS/NIFM filtered connectivity and launcher HTTPS fallback: PASS")
