// SPDX-License-Identifier: GPL-3.0-or-later
// Unified domain denylist shared by PS5 host resolver and emulated Switch DNS.
// Loaded once from the app's immutable, packaged network-hosts.txt on startup.
#pragma once
#ifdef __cplusplus
extern "C" {
#endif
// Return 0 only after successfully loading a nonempty validated list.
int eden_network_filter_load(const char* path);
// Nonzero means BLOCK. Failure to load policy intentionally blocks all DNS.
int eden_network_host_blocked(const char* host);
unsigned eden_network_filter_count(void);
#ifdef __cplusplus
}
#endif
