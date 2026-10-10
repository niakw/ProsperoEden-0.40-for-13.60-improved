# Eden Encore — R302 upstream fixes and integrated dependencies audit

**Audit date:** 11 October 2026. **Branch:** `dev/ps5-sparse-jit`; release `fix/0.40-zbic-13.60` unaffected. **Baseline:** R301 all-on native build SUCCESS at `eb566f1ef54046fc4ced9f2dd0eb95a0ce6ea536`. R302 has **not** been qualified by a PS5 run at this report's creation.

## ProsperoEden main (blackbearreloaded/ProsperoEden)

Reviewed source commit history on main through **0dd9dd0fd343** (10 October 2026 21:04 UTC). The parent is **not** directly mergeable blindly: Eden Encore has a different launcher, per-title config, crash/log architecture, native memory and injected GPU patches.

### Adapted and implemented in R302

| Upstream | Priority | R302 adaptation | Real test remaining |
|---|---|---|---|
| [0dd9dd0](https://github.com/blackbearreloaded/ProsperoEden/commit/0dd9dd0fd343e665cd8a16e9a366c6c177e358d2) #102 | High: GPU watchdog/device lost | Replace Eden's complete Android/non-Android draw-submit threshold block with `DRAWS_TO_DISPATCH = 512`; **retain** Encore's pre-existing configurable GPU worker dispatch mask, including the current 8-draw default. This changes maximum Vulkan command-buffer length but not the worker's normal draw handoff cadence. | Hardware GPU submission stress, FC27 + BOTW textures and shader-heavy scenes; frame intervals may change in either direction |
| [673f675](https://github.com/blackbearreloaded/ProsperoEden/commit/673f6759f6fffa505525db27c8f4f570637f0c52) #72 | High: shader-cache truncation/reboot loops | Port `shader_cache_reader.inc` to the **same pinned** Eden `shader_environment.cpp`, validating shader count and environment sizes, salvaging the last complete entry and truncating bad tails, rather than deleting all valid entries after a crash. Port host fixture and generated CMake replacement. | SDK native linking plus real cache corruption/recovery |
| [1f7fcf36](https://github.com/blackbearreloaded/ProsperoEden/commit/1f7fcf3666c8046ee0999f23f7ce5d5321c824f7) #95 | Medium: 120Hz on VRR screens | Revert requested 119.88/120Hz only for a stable 15–18.5ms (60Hz) vblank period; a 48Hz idle VRR period alone is not reason to revert. This only affects a requested high refresh mode. | Hardware 60Hz fallback and true VRR 120Hz display tests |

All are **source-ported** rather than cherry-picked as entire upstream commits: our generator, logging switches, GPU instrumentation and visual design are not overwritten. `tools/check-ps5-upstream-fixes-r302.py` tests real included shader-cache loader with a C++20 mock and guards source adaptation. Host builder now also builds and runs `eden-shader-cache-check`.

### Reviewed, NOT blindly imported

- [0d2510d](https://github.com/blackbearreloaded/ProsperoEden/commit/0d2510d6fa501e89a6a8031e491bc18e1e905d6d) (log flush): Encore already has a custom ring/pipe-based, dynamically toggled log implementation plus accepted-network audit. Replacing it with upstream's unrelated one-second fflush strategy could reintroduce stalls or lose crash breadcrumbs; keep ours pending a demonstrated OS-level pipe failure.
- [7d9303a](https://github.com/blackbearreloaded/ProsperoEden/commit/7d9303a1adba3c4da44b5489b98a0fb84d87f675) (one data root/no silent sandbox fallback): Encore's explicit storage root, migration and recovery differ. The principle is important, but requires a migration plan for already installed FW13.60 users and no save-loss; no blanket transplant.
- [dfda802](https://github.com/blackbearreloaded/ProsperoEden/commit/dfda8026d41c9e5116c02310a1fa5a7601f71fbc) (Lapy target lifetime): ours uses existing elevation path rather than pinning this exact helper. Requires independent donor lifecycle/safety and firmware 13.60 testing.
- [2beb1b5](https://github.com/blackbearreloaded/ProsperoEden/commit/2beb1b538cc327f00a26825ee1eef44adb6eaa2e) and [75dc3a8](https://github.com/blackbearreloaded/ProsperoEden/commit/75dc3a8383a69781b2e72e1cec0a4aad8c24c6de) (Eden/Vulkan/Mesa/SDK pins): upstream temporarily moved Eden to 67bada77 then reverted to `5f142c79`; Encore **already pins 5f142c79**, so there is no Eden upgrade needed. Backend pin upgrades also require shader/present/lifetime correctness tests.
- [8e23d8a](https://github.com/blackbearreloaded/ProsperoEden/commit/8e23d8a2f46c9a0b2f5372b57eca0838665751eb) (handheld port 8 leakage): relevant controller bug, but Encore has its own PlayStation mapping/dual controller scheme; investigate against approved glyph and navigation controls rather than copying it unreviewed.
- [fef2899](https://github.com/blackbearreloaded/ProsperoEden/commit/fef2899c542e0249bcfda02ab37c0766ba0dee36) (cheats main-module registration): worthwhile later if title-cheat support is demonstrated broken, unrelated to FC27 lag.
- Frame generation [f107023](https://github.com/blackbearreloaded/ProsperoEden/commit/f107023aacd415df14980ae4c18319291e5b89a0), [a7b51b0](https://github.com/blackbearreloaded/ProsperoEden/commit/a7b51b0d5f8c7572bee1c24f0f156f9742da9e74) and [e6b58c0](https://github.com/blackbearreloaded/ProsperoEden/commit/e6b58c054b05f884ebddc8a6764b8b3103fc406f): not a CPU emulation speed fix; requires runtime libraries and display validation; do not conflate generated frame count with FC27 running faster.

## Other integrated projects, inspected on 11 October 2026

| Dependency | Encore pin | Latest inspected branch and fix leads | Decision |
|---|---|---|---|
| [Eden mirror](https://github.com/eden-emulator/mirror) | `5f142c79` | `67bada77`: non-NVIDIA fragment shader workaround; older upstream fork reverted to 5f. | Keep pinned until GPU shader regression tests |
| [PS5_Vulkan](https://github.com/mihawk-99/PS5_Vulkan) | `3f3ee696` | `252bf912`: Mesa refresh changes; GPU broker/host-visible memory support | Keep custom PS5 native frontend and current WSI patch; port specific needed behavior |
| [PS5_Mesa](https://github.com/mihawk-99/PS5_Mesa) | `0b2d6d1a` | `47e9eb61`: high-refresh offer/acceptance, framebuffer handling. | Avoid bulk RADV upgrade without memory/lifetime qualification; R302 ports narrow VRR condition |
| [PS5_PayloadSDK](https://github.com/mihawk-99/PS5_PayloadSDK) | `95c08f27` | `e879f15` file descriptor-limit handling, `3752be7` heap-lock telemetry, `67e61b1` CPU topology probe | Worth targeted review; global SDK bump changes libc/heap and CPU assumptions |
| [ps5-opengl](https://github.com/blackbearreloaded/ps5-opengl) | `ad2807d4` | Latest commits mostly CI/cache/SDL fixes; release pin intentionally isolated | No urgent native Vulkan fix identified |
| [ps5-native-app-boilerplate](https://github.com/blackbearreloaded/ps5-native-app-boilerplate) | `dd44bbdc` | `38c68b46` safe self-update backup | Nice later; no FPS fix |
| [zbic](https://github.com/kinnay/zbic) | `11b08f27` | Still matches latest head | No changes |
| [PS5-Lapy-JB-Daemon](https://github.com/blackbearreloaded/PS5-Lapy-JB-Daemon) | Not pinned by Encore | Parent uses a newer `57fcc19` helper from a different fork, needs lifecycle validation | Do not change root/elevation path during GPU performance pass |

## Ship gate

The already validated R301 test binary remains available. R302 **host/source preflight [#38094355017](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38094355017) completed SUCCESS**, including the executable actual shader-cache-reader corruption fixture, Sony memory sanitizers, Vulkan source contracts and UI/network checks. This commit launches a separate **native PS5 All-On build** of R302; do not publish or change the shipping branch. Native compilation and console testing are not assumed green. Green SDK/host tests are **not** evidence of an FC27 frame-time gain or 13.60 GPU/memory safety. Compare same scenes and shader-cache states; expected #102 trades shorter GPU submissions for more frequent flushes, so its measured effect can be positive or negative.
