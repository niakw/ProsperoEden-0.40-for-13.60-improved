# Eden Encore R295 — Application-wide domain hosts policy

Date: 10 October 2026. Branch `dev/ps5-sparse-jit`. Applies to the **PS5 native build**.

## Goal

Replace the legacy **all-guest-Internet-disabled** configuration with a
packaged domain denylist, shared by Switch-game DNS requests and launcher
network requests. Normal external domains remain resolvable. This is a
domain-based control, **not a packet firewall**.

The policy is at:

`headless/network-hosts.txt` → deployed as `/app0/network-hosts.txt`
(or the same file in Eden's detected mounted application directory).

It includes **145 entries**, consolidated from the supplied Nintendo,
Epic, EA, Ubisoft, Rockstar, Microsoft, Sega, Capcom, CDPR/GOG and
other publisher/service hostnames. Redundant names are removed because
a plain domain covers all its subdomains:

- `ea.com` blocks `ea.com`, `api.ea.com` and `login.api.ea.com`.
- `nintendo.net` blocks `s01.lp1.u.npln.srv.nintendo.net`,
  `ctest.cdn.nintendo.net` and their descendants.
- `epicgames.dev` blocks `api.epicgames.dev`.
- `gearboxsoftware.com` blocks `shift.gearboxsoftware.com`.
- `scsi-upload-lp1.s3.us-west-2.amazonaws.com` is listed explicitly
  and does not block unrelated AWS S3 addresses.

Rules are case-insensitive, strip a DNS terminal `.`, match complete
DNS-label boundaries and reject malformed input. `not-ea.com`,
`ea.com.evil.org` and unrelated `api.nlib.cc` must **not** be blocked.

## Wildcards

One rule per line, `#` for comments, with `*` supported in individual
DNS labels. For example:

- `*.*test.fr` matches `foo.alphatest.fr`
- `*.test.*` matches `api.test.fr`, `web.test.org`

Each `*` matches zero or more characters **within one label**, never
a `.`. All rules, even wildcards, implicitly cover an arbitrary number
of preceding subdomain labels. Explicit `*.` is therefore unnecessary
for ordinary suffix rules. This is a custom application-domain file,
**not** an operating-system `/etc/hosts` parser.

## Integration

- Native launcher: `headless/ps5_net_compat.c` checks
  `eden_network_host_blocked` before `getaddrinfo` and
  `gethostbyname` perform any host lookup, including redirects that
  require a new DNS resolution.
- Emulated titles: a separately hashed patch
  `eden-ps5-guest-domain-filter.patch` resets the legacy guest
  `kGuestNetworkOffline` to `false` and checks **both** Nintendo
  `sfdnsres` DNS IPC entrypoints. BSD socket creation and NIFM remain
  operational for allowed destinations; the forced airplane-mode reset
  in `headless/main.cpp` is disabled.
- One policy implementation in
  `headless/network_domain_rules.c`, linked to the executable,
  referenced by both native and guest-resolution paths.
- Fail closed at startup: the packaged file must exist, be valid and
  contain at least one rule. The app refuses to continue when loading
  fails instead of silently enabling unrestricted DNS.
- The prior offline backport is intentionally left intact for a
  reproducible cached-source migration. The new domain-based delta gets
  its own receipt and validator.

## Important network limits

This **cannot guarantee** that all communications to the organizations
above are blocked. Domain names alone cannot reliably identify packets
sent directly to **numeric IP addresses**, already-established sockets,
hardcoded IPs, encrypted DNS (DoH/DoT) sent to an unrelated host, or
traffic over endpoints hosted on a different domain. CDN/IP address
sharing also makes domain-to-IP blocking inappropriate without a more
sophisticated firewall/proxy layer.

It also does not restrict PS5 system services outside the Eden Encore
process, another console app, or a privileged network stack bypassing
these resolver entrypoints. The native host resolver is IPv4-oriented
on the targeted SDK. No claim of packet-level isolation is made.

**For complete anti-telemetry coverage**, retain an external DNS/firewall
policy on the console/router in addition to this in-application list.
Network allow-by-default may permit a game to attempt online sign-in
at a domain not yet on this list; this may fail at protocol/service level.

## Validation before a console test

`tools/check-network-domain-policy.py` compiles the actual C matcher and
checks apex, inherited subdomains, mixed-case, spoof suffixes, wildcard
labels, exact third-party cloud hosts, permitted Nlib/GitHub and
fail-closed behavior. The CI source test checks package inclusion,
host-resolver wiring, guest DNS routes and all-title network policy.

A PS5 SDK build is still needed. A real device test must separately
check DNS for `api.ea.com` (denied), `api.nlib.cc` (allowed),
and an explicitly allowed **game** hostname to confirm guest sockets
and NIFM behave correctly on firmware 13.60.
