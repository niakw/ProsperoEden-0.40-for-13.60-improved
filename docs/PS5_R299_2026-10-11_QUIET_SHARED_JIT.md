# Eden Encore R299 — quiet shared A64 JIT and CPU dispatch bookkeeping

Date: 11 October 2026. Development-only branch: `dev/ps5-sparse-jit`.
Native PS5 firmware 13.60. R299 is **not yet a hardware-validated performance fix**.

## Input evidence and motivation

The earlier FC27 5-second windows contain two different slowdowns: (a) peaks
where compilation is material, and (b) late windows near 12–16 FPS with only
~26–81 ms of aggregate JIT compilation, while three guest CPU workers remain
busy for most of each 5-second window. Summed worker times overlap and cannot
be treated as wall elapsed time. R299 removes latent diagnostic overhead but
does not establish the true guest PC/HLE hot spot.

R298 optimized the pinned native Dynarmic compile timer, A32 callback counters
and GPU detailed profile, but `headless/dynarmic/jit_impl.inc` and
`jit_group_support.inc` still had independent shared-A64 diagnostic paths:

- Four JIT clock probes per newly compiled A64 block, unconditionally.
- Per-dispatch / lookup / hit / contention `fetch_add` operations against
  development counters, even when detailed logging was disabled.
- An unconditional monotonic clock pair and two synchronous printf calls on
  group cache clears; bounded pressure prints also ran in quiet mode.

## Changes on this branch

1. The shared-JIT compiler takes an opt-in Detailed Logging snapshot per
   compile and only then samples start/translated/optimized/emitted timings
   and reports compilation phases.
2. The shared group `EdenCount` checks the existing weak
   `eden_native_detailed_logging()` runtime preference and does not write
   shared counters in silent gameplay. Turning Detailed Logging ON enables
   subsequent path counts immediately; OFF ceases future writes.
3. Cache-clear timing and printouts, and pressure printouts, require Detailed
   Logging. The actual cache-clear, halt/quiescence, epoch and invalidation
   logic is **unchanged**. The core evacuation counter remains available.
4. Extended `tools/check-ps5-quiet-jit-timers.py` with an extracted real
   C++20 `EdenCount` regression covering 100,000 quiet calls, logging ON,
   logging OFF, and per-core counting. Source guards cover the shared A64
   compile/clear gates. This is host evidence, not a PS5 benchmark.

## Preserved requirements

- No change to executable-memory aliasing, sparse JIT commit sizing, PS5 system
  RAM reservation, guest instruction correctness, GPU/shader accuracy, video
  resolution, UI styling, profiles, mappings, or network-hosts rules.
- A weak or absent runtime logging callback means silent mode; no unresolved
  strong dependency was introduced into the generated native JIT.
- Do not interpret silent missing path counters as measured zero: telemetry is
  disabled, not evidence of an idle worker. Use deliberate short diagnostic
  captures to inspect JIT paths when necessary.

## Validation gates and next actions

- R298 PS5 all-on native build [#38091399837](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38091399837)
  completed SUCCESS, with matching test-app and symbols artifacts; it compiled
  commit `45963a8b` **before R299**. It cannot validate R299.
- R299 host source-only preflight [#38092108026](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38092108026) completed **SUCCESS** including C++20 real-fragment shared-JIT counter test, Sony mspace UBSan/TSan, approved UI checks and the diff gate.
- The separate native PS5 all-on build is requested by this documentation-only
  commit and must finish before R299 installation or FC27/BOTW comparisons.
- Identify the actual late-match CPU guest/hot-block source with bounded
  opt-in sampling, accurate time-window alignment and HLE/kernel wait
  classification. Compare identical gameplay scenes, same graphics settings
  and warmed shader cache; never claim stalls fixed from CI alone.
