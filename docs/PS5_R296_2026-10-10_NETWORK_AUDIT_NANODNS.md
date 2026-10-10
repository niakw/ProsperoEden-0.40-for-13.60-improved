# Eden Encore R296 — No DNS override and opt-in accepted-network audit

Date: 10 October 2026. PS5 native test branch integration only; requires
successful native build and console validation.

## Non-interference with NanoDNS and external DNS

**Nothing in this feature edits PS5 DNS settings, resolv.conf, router
settings or NanoDNS configuration.** R295's domain filter is exclusively an
application-local hostname precheck:

1. **Denied hostname:** return the existing DNS-not-found error locally.
   Neither the native host resolver nor the emulated game's DNS resolver
   transmits the denied query.
2. **Allowed hostname:** execute the **original** DNS resolution path
   unchanged. In the launcher this remains `sceNetResolverStartNtoa`;
   in a game this remains the pinned Eden `Network::GetAddressInfo`.
3. Upstream system/global DNS—including NanoDNS—can still deny, redirect
   or fail the query. Eden does **not** interpret "allowed by its own list"
   as permission to bypass those upstream restrictions.
4. Raw-IP socket traffic is still possible because a hostname-only policy
   cannot infer what company operates a direct destination IP. The new
   audit helps identify these cases; it is not a substitute for an external
   DNS or packet firewall.

This policy affects **only the Eden Encore process** and its emulated games;
it cannot control unrelated PS5 apps or background console services.

## Detailed Logging controls the only new file

On the first accepted/denied request **when Detailed Logging = ON**,
the process lazily creates:

`Eden::LogsDir()/network-accepted.log`

Each event has the form:

```text
epoch=... scope=launcher event=dns-resolved target=api.nlib.cc bytes=0 status=0
epoch=... scope=guest event=dns-allowed target=updates.example.org bytes=0 status=0
epoch=... scope=guest event=dns-denied target=api.ea.com bytes=0 status=1
epoch=... scope=guest event=connect target=203.0.113.10:443 bytes=0 status=0
epoch=... scope=guest event=tx target=fd:12 bytes=516 status=0
epoch=... scope=native event=rx target=203.0.113.22:443 bytes=1200 status=0
```

The examples above describe the format, not evidence of actual network
connections. `dns-allowed` means **Eden's local list allowed an attempt**,
not that the configured DNS server resolved it or that packets reached a
remote server. `dns-resolved` and `dns-error` report outcomes from the
native launcher resolver; game-side calls are recorded at their DNS IPC
entry boundary. `connect` means a socket connect returned success or a
nonblocking in-progress status; it does not guarantee a completed handshake.
`tx/rx` counts **successful bytes at a socket API boundary**, not packets
observed on the network wire. The API may batch or split wire packets.

The file stores **no payload, passwords, Authorization headers, complete
URL paths, TLS plaintext, cookie headers or packet contents**. Hostnames,
IP addresses, ports, file descriptors and byte counts are logged; as such
logs can still expose contact metadata and should not be shared publicly
without review.

**Important:** the guest HLE and native BSD wrappers may
both observe parts of the same socket flow. To avoid misleading totals,
the records preserve `scope=guest` versus `scope=native`; do not sum
these scopes as unique on-the-wire bytes.

A buffered 32 KiB writer flushes approximately every 64 records. It keeps
one active file of at most approximately 4 MiB and one previous segment
`network-accepted.log.prev`. There is no synchronous per-packet fsync,
no file created in silent mode, and no per-packet timestamp formatting
when silent. Turning Detailed Logging OFF closes the writer immediately;
re-enabling it resumes only from that point. On the next quiet startup,
old nonfatal network-audit segments are cleaned up, like other routine logs.

## Implementation and test boundaries

- `headless/network_audit.c`: app-local buffered, lock-protected,
  atomic-gated metadata journal. No DNS configuration or packet mutation.
- `headless/ps5_net_compat.c`: log native resolution results without
  changing the request, return value or system DNS selection.
- `headless/network_audit_sockets.c`: process-local link-time
  `--wrap=connect/send/sendto/recv/recvfrom`; forwards the exact
  arguments, stores/restores errno, logs successful operations only.
- Native CMake derivation wraps **game HLE** DNS/Connect/Send/SendTo/Recv/
  RecvFrom paths, retaining their existing results, buffer bytes and socket
  ownership. Any mismatch with the pinned Eden code is fatal at CMake
  preparation, never silently skipped.
- Runtime toggling reuses the existing Detailed Logging preference.
- `tools/check-network-accepted-audit.py` host-compiles the actual writer,
  verifies silent startup, opt-in, live-off stop, bounded rotation,
  log-line escaping and source-level no-DNS-override constraints.
- `tools/check-ps5-net-unit.py` links the logger in quiet mode so the
  existing native resolver host fixture continues to validate the real
  R295 filter and the upstream DNS lookup path.

**Coverage limitation:** application APIs using other network entry points
(not reached by these HLE or POSIX wrappers) will not appear in the audit.
These logs are intended to find unexplained allowed network traffic, not
to assert complete packet or system-wide capture. Router/NanoDNS/firewall
logs remain authoritative for traffic outside the intercepted APIs.

No FC27 or BOTW benchmark result has been inferred from these source changes.
The logging path remains disabled in normal gameplay.
