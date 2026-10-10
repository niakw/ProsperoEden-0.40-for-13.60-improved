# Eden Encore — PS5 R301: quiet guest JIT Run entry

**Date:** 11 October 2026. **Development:** `dev/ps5-sparse-jit`.
**Firmware target:** PS5 13.60. **Status:** source changes, not yet a measured hardware gain.

## Evidence

In the pinned `headless/CMakeLists.txt` A32/A64 Dynarmic adaptation, the DEV
build previously evaluated `GetPC()/Regs()[15]`, `GetSvcNumber()` and
`GetFpcr()/Fpscr()` and called `SampleCpu()` **twice per guest JIT Run**
even with Detailed Logging OFF. `SampleCpu` itself checks whether a new
snapshot epoch was requested, but this was too late to avoid argument reads,
dispatch calls and atomic loads on quiet runs.

The supplied FC27 logs include sustained 5-second intervals of ~15–17 FPS with
relatively little new JIT compilation and heavily occupied guest CPU workers;
these are **not** evidence that this diagnostic overhead alone caused the
problem. The original logs include no reliable physical GPU occupancy.

## Implementation

- Snapshot the existing `detailed_gpu_profile` relaxed atomic at guest
  `Run` entry, and skip both `SampleCpu` calls **and argument evaluation**
  while detailed logging is OFF.
- Preserve the original guest `m_jit->Run()` exactly once, the returned
  halt-reason translation, and both `cpu_state[m_core_index].phase.store`
  transitions. The watchdog still knows whether a guest CPU is in its
  emulated Run or kernel phase.
- Enabling detailed logging makes sampling active from the next Run; disabling
  detailed logging stops sampling on the next Run. A toggle during a single
  Run takes effect at its next entry.
- The update is global for both A32 and A64, not a FC27-only workaround.
  CPU affinity, JIT capacities, sparse RW/RX mappings, memory reservations,
  GPU rendering, UI and network-hosts rules are unchanged.

## Tests

`tools/check-ps5-quiet-guest-entry.py` extracts the **actual CMake
replacement body** for A64 and A32, compiles each into a C++20 mock and checks
40,000 quiet Run executions (zero guest register and service-number reads,
zero profiler callbacks), ON/OFF toggles, preserved watchdog phases, one
guest Run per call and unchanged halt result.

This is host/source verification; the exact changes still require SDK
compilation and console verification. Keep the shipping branch unchanged.

## Native build and test gate

R300 all-on build [#38092774003](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38092774003)
completed SUCCESS and published the checked native app and unstripped crash
symbols. It does **not** contain R301.

R301 host preflight [#38093318961](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38093318961) completed **SUCCESS**, including the actual A32/A64 generated-wrapper C++20 test, memory sanitizers, UX and source-diff validation.

The next commit requests a new **native all-on SDK build** of this source with `publish=false`, preserving its exact source SHA and symbol provenance. Its success and performance are not assumed.
Do not change FW13.60 PS5 resolution or memory safety limits to claim an
unmeasured performance fix.

The optional `pc-sample.txt` signal-profile handler uses register offsets
documented on PS5 firmware 6.02; it is not yet qualified on 13.60. Leave it
disabled for the first gameplay comparison.

A real FC27/BOTW hardware test is still necessary to measure late frame
intervals, workload attribution, texture correctness, application lifetime and
controller glyph issues.
