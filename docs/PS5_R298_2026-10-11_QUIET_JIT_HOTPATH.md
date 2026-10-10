# Eden Encore R298 — quiet JIT hot paths and retained FPS diagnosis

Date: 11 October 2026. Branch: `dev/ps5-sparse-jit`. Native PS5 13.60
test-only. No measured hardware performance gain yet.

## Scope and evidence

Earlier user-provided FC27 logs show TWO independent classes of stutter:
- A large transient miss where three host JIT workers collectively spent
  ~9.93 seconds compiling in a ~5 second measurement window, concurrent
  with ~4.58 seconds of GPU producer back-pressure. These times overlap
  among threads; they cannot be added as elapsed wall time.
- Late-match windows as slow as ~12–16 FPS with only ~26–81 ms aggregate
  JIT compilation across five seconds, GPU worker idle ~4 seconds, and
  three guest CPU worker owner clocks each near 5 seconds. That suggests
  CPU-side guest execution/service/synchronization work can dominate even
  once translation is already cached. This does NOT establish the hot
  guest instruction/function or physical PS5 GPU utilization.

R298 does not pretend to cure both causes without console evidence.

## Changes

1. Developer all-on builds used to read `steady_clock::now()` at entry
   and exit of **every newly compiled A64 Dynarmic block**, regardless of
   Detailed Logging. R298 creates `EdenCompileTimer` with an explicit
   `active` snapshot and samples the clock only if logging was on at timer
   construction; verbose samples and totals remain available when asked.
   The weak `eden_native_detailed_logging()` gate is defined in the PS5
   native main runtime and follows the already supported live preference.
2. The first 200 `EDEN_JIT_PRESSURE` messages per guest core used to print
   a line with a monotonic-clock query on each whole-cache evacuation
   even in quiet mode; these lines now require Detailed Logging as well.
   The low-cost evacuation counter itself remains for diagnostics/crash
   breadcrumbs. Actual memory growth/evacuation logic is unchanged.
3. A32 C++ slow-path memory callbacks previously incremented shared
   development atomic counters even in quiet gameplay. Such counters
   now update only when detailed profiling is enabled. Memory reads,
   writes, exclusives and guest-state semantics are otherwise identical.
4. When Detailed Logging changes in the launcher, synchronize the
   `detailed_gpu_profile` hot-path gate immediately so turning logging
   OFF stops GPU/JIT diagnostic counters without restarting Eden.
5. Added an executable C++20 regression:
   `tools/check-ps5-quiet-jit-timers.py`. It compiles the exact source
   fragment emitted by the pinned native CMake generator, verifies quiet
   timers never initialize their timepoint, and validates no A32
   callback counter updates outside verbose mode. The CI also retains
   R291–R297 source tests and the native worker/queue probes.

## Preserved safeguards

- No JIT pool expansion beyond memory admission or native 2 MiB sparse
  commit policy; PS5 system-reserved RAM is untouched.
- Per-core Dynarmic, compilation batching and unsafe shared JIT remain
  unchanged. Automatic speculative batching is not proven to reduce
  low-JIT late-match stutter and could worsen guest correctness.
- No forced 60 FPS, GPU accuracy downgrade, rendering resolution change,
  design/glyph/UI modification or title-specific fast path.
- Network `network-hosts.txt` now explicitly includes `microsoft.com`
  and `phoenix-api.wbagora.com` (including all descendants), with
  package matcher regression coverage and independent NanoDNS/global DNS
  unchanged. The launcher and games use the same domain policy.
- The verified R296 compiled app predates R297/R298; a new PS5 build
  and subsequent matched FC27/BOTW hardware tests remain necessary.

## Remaining performance gates

The late-match CPU saturation needs *real* native guest PC/function
samples and independently measured guest/kernel/HLE wait ownership;
GPU-owner idle counts cannot establish GPU hardware occupancy. Keep
shader caches warm and record identical match scenes, game profiles and
present frame intervals. Do not claim stutter eliminated until
on-console sustained-gameplay results support it.
