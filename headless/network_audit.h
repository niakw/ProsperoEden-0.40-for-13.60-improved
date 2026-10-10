// SPDX-License-Identifier: GPL-3.0-or-later
// Optional, application-scoped network metadata audit. No packets or DNS are
// modified by this interface; quiet mode performs no filesystem I/O.
#pragma once
#ifdef __cplusplus
extern "C" {
#endif
// Configure once before network startup. Does not create a file when OFF.
int eden_network_audit_init(const char* path, int detailed);
// Applies a live Settings > Detailed Logging change, closing the file on OFF.
void eden_network_audit_enable(int detailed);
// Network boundary metadata only: no payloads, URL paths or credentials.
// scope="launcher"/"guest", event="dns-allowed"/"dns-blocked"/"connect"/
// "tx"/"rx"; target is hostname, IPv4:port or "fd:N".
void eden_network_audit_event(const char* scope, const char* event,
                              const char* target, unsigned long long bytes,
                              int status);
#ifdef __cplusplus
}
#endif
