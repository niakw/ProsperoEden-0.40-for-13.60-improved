# Eden Encore R300 — quiet guest CPU idle, IPC, GPU synchronization and file I/O

Date: 11 October 2026. Development branch `dev/ps5-sparse-jit`. Firmware PS5 13.60. Source-only changes pending real native SDK and on-console validation.

## Evidence and reason

R298/R299 stripped several development hot-path timings. A source audit still found five CMake-generated native paths that sampled two clocks and wrote development counters even while Detailed Logging was OFF:

1. `PhysicalCore::Idle` always read `NowNs()` around every guest idle wait and called `CountIdle`. It can execute on frequent cross-core handoffs.
2. `nvhost_ctrl` GPU fence registration captured a timestamp even for silent execution; its asynchronous callback later called `AddSince`.
3. `buffer_queue_producer` dequeue measured the complete `WaitForFreeSlotThenRelock` call.
4. `svc_ipc` measured every `SendSyncRequest` (including kernel/HLE service processing).
5. `fs_i_file` and `fs_i_storage` measured every guest file read, incremented global counters and formatted a per-read file trace, even though crash-only logging was enabled.

These are **potential** CPU overheads and do not establish the cause of late FC27 stutters.

## Changes

- Use the existing `Eden::Performance::detailed_gpu_profile` live atomic to snapshot detailed mode before a timed request. When quiet, start timestamp is zero and no end clock, diagnostic counter write or per-read formatting occurs.
- The idle spin/wait logic, condition variable, wake predicates and interrupt semantics are identical. `CountIdle` is only called for opted-in captures.
- Keep GPU syncpoint action registration, callback execution and buffer-queue dequeue identical. Only profiling `AddSince` is gated.
- Keep IPC `SendSyncRequest` result/ordering identical; no bypass of HLE or network policy.
- Keep `IFile` and `IStorage` backend reads identical. Crucially, short storage reads still emit `EDEN_FS_SHORT_STORAGE` unconditionally; only verbose normal-read/open logs and time/byte accounting are silenced.
- Include `performance.h` in the generated filesystem-open source so its optional diagnostic gate compiles.

## Tests and confidence

- Added `tools/check-ps5-quiet-cpu-io-clocks.py` to **both** host-only source regression and native prebuild workflows.
- The test extracts and compiles the real CMake-generated `PhysicalCore::Idle` replacement in a C++20 mock and checks 10,000 calls with diagnostics OFF, a live ON toggle, and another 10,000 calls OFF. It audits the exact source-generation sites of syncpoint, dequeues, IPC, file reads and unconditional storage short-read detection.
- These host checks do not measure PS5 scheduling, threading, frame time or correctness of compiled native SDK variants.

## Pre-test qualification and boundaries

- R299's unfinished native compilation was superseded when the development branch advanced: the workflow's `cancel-in-progress` cancels intermediate native runs on subsequent commits. Only the final R300 native build can validate R300 source generation.
- Run full source/host preflight, then one independent native all-on compilation on the final commit. Keep the exact binary SHA and ELF symbols. **Do not** publish a release.
- Next real PS5 tests must compare FC27 gameplay and BOTW in the same scenes, shader-cache state and graphics presets. Compare frame interval tails as well as FPS; don't claim GPU use or jitter fixes from a green build.
- Do not alter graphical accuracy, default profiles, 16 GiB unified-memory safety, reserved system memory, glyph art, DNS hosts, NanoDNS integration, UI, delivery branch or title-specific code.
