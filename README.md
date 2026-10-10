<p align="center">
  <img src="assets/icon0.png" width="180" alt="Prospero.Eden Encore logo">
</p>

<h1 align="center">Prospero.Eden Encore</h1>

<p align="center">
  <strong>The PS5 13.60-focused continuation of ProsperoEden 1.000.040.</strong><br>
  Stability first. Newer game support. Better recovery. Better PS5 UX.
</p>

<p align="center">
  <img alt="PS5 firmware 13.60 target" src="https://img.shields.io/badge/PS5%20firmware-13.60%20TARGET-2ea44f">
  <img alt="ProsperoEden base 1.000.040" src="https://img.shields.io/badge/base-ProsperoEden%201.000.040-6f42c1">
  <img alt="ZBIC and LZ4" src="https://img.shields.io/badge/NSO-ZBIC%20%2B%20LZ4-blue">
  <img alt="DualSense first" src="https://img.shields.io/badge/UX-DualSense--first-8250df">
</p>

> [!IMPORTANT]
> **PS5 firmware 13.60 is Encore's primary hardware-tested target.**
> Other firmware versions are not currently claimed as validated by this fork.

## Why Encore?

Current ProsperoEden releases moved beyond the 1.000.040 base and use a newer Lapy-based elevation path. That newer direction brings useful features, but **13.60 is not one of the firmware versions currently validated by upstream's Lapy helper**.

Encore takes the opposite approach: keep the **known-working 1.000.040 filesystem-access path on 13.60**, harden it, simplify storage to one root with one fixed layout, then selectively add compatibility, stability, recovery and usability improvements that are valuable on a PS5 today.

The result is not a blind downgrade and not a blind merge of newer upstream code. It is a **13.60-specific maintained branch** with its own hardening and release validation.

## Developer-branch update — 10 October 2026 (not released)

The latest `dev/ps5-sparse-jit` work includes **R294** (stop-aware, event-driven
GPU command queue waits, crash-only GPU watchdog evidence, and opt-in cache lock
timings) and **R295** (one packaged hostname denylist for the PS5 launcher
and emulated Switch DNS).

- `headless/network-hosts.txt` ships inside the app as `network-hosts.txt`;
  145 publisher-domain rules cover matching subdomains, with `*` glob
  support within DNS labels. For example, `ea.com` blocks `api.ea.com`.
- The previous blanket guest-network shutdown and forced airplane mode are
  removed from the PS5 test build; permitted hostnames remain resolvable.
  Existing Nlib cover and banner HTTPS stays available.
- This is **not a firewall**: direct IP traffic, DoH and domains not included
  in the file can bypass DNS-only filtering. Use external network controls
  for stronger protection.
- Developer host tests validate the parser, guest/launcher integration and
  native DNS shim; PS5 firmware 13.60 behavior and real gameplay gains
  remain to be qualified.

For full caveats and test gates see [R294 GPU queue notes](docs/PS5_R294_2026-10-10_GPU_QUEUE_STOP_WAIT.md)
and [R295 domain policy](docs/PS5_R295_2026-10-10_UNIFIED_DOMAIN_HOSTS.md).

## Local integration audit — 8 October 2026 (not released)

The latest downloadable build and the current **local audit candidate** are different states.
The local candidate is on `local/no-build-polish` (base `149df7a`), has **not** been built or booted
on PS5 and is **not** available in the current downloadable package. Its changes include:

- A wider TV-first Home with Nlib artwork requests decoupled from library enumeration, four utility
  tiles, and a selected-game Quick Settings overlay. Host static checks do not prove the final PS5 image.
- Native IPv4 DNS and socket-flag compatibility for Nlib HTTPS, bundled CA verification retained,
  and additional network ABI/sanitizer tests. Actual PS5 HTTPS and banner retrieval remain untested.
- Bounded rotating logs (8 MiB first and recent segments per stream), improved failure handling,
  and a protected release hot path; logs retain useful recent evidence without unbounded growth.
- An additional package `icon0.dds` candidate for the PS5 system overlay. Its on-console effect
  remains **unverified**.
- Three optional **disabled-by-default** kernel/JIT/HLE experiments: dummy host-thread waits,
  cross-core I-cache coherence and the ServiceManager/audio initialization backport. They are
  deliberately excluded from the first baseline, pending independent PS5 A/B validation.

**Performance workstream:** see [CPU/HLE stability and 30→60 FPS research](docs/PERFORMANCE_ROADMAP.md). The candidate has an offline analysis tool for identifying repeated guest-PC samples and presentation gaps. **No FPS increase or interpolation feature is shipped yet.**

**Known unresolved problem:** FC27 can keep presenting at about 30 FPS while its guest/gameplay
stalls. A smooth-looking FPS counter does not prove guest progress; the cause is not yet established.
Frame generation to 60 FPS would be a separate display feature, **not** a freeze fix. A passing
native build alone is not sufficient for release: actual boot, network, overlay, UI navigation and
extended gameplay tests on firmware 13.60 remain mandatory.

## PS5-first execution architecture — developer branch (not released)

The FC27 A/B/C/D campaign is finished. B and especially C reduced observed
JIT cache pressure and improved average frame presentation, while CPU logical
pinning in D did not provide a convincing general benefit. Some gameplay stalls
remain, including stretches below 25 FPS without an adjacent JIT-pressure event.

The isolated `dev/ps5-sparse-jit` branch now includes:

- **One global PS5 JIT memory budget for all A64 and A32 titles.** At launch,
  Eden queries the available contiguous direct-memory pool and distributes a
  continuously sized initial code-cache budget among the guest cores, after
  leaving physical headroom for system, game and GPU. No FC27 whitelist or
  A/B/C hard-coded ceiling remains. Safe Launch or a failed memory query
  reverts to the proven baseline. This policy is present in normal builds and
  requires no manual performance switch. Each code arena remains constrained
  by Xbyak/x64 addressing; the current allocator is still physically dense,
  so true on-demand multi-arena growth remains separate unfinished work.
- PS5-native Vulkan shader worker budgeting and one-time worker-count receipt,
  not yet measured on hardware. A smaller pool may slow shader warmup.
- Global **on-disk shader cache retention**: RADV quota follows its actual
  backing filesystem's free-space budget rather than 256 MiB; OpenGL cache
  records are pruned oldest-first only when writable storage is genuinely
  short, not at an unconditional 64 MiB ceiling. Neither policy changes GPU
  RAM capacity or guarantees shader warmup improvements.
- GPU/direct-memory snapshots at core initialization and shutdown, with a conservative
  distinction between largest contiguous block and total-free upper bound.
  No unproven GPU budget increase has been applied.
- A provisional sparse JIT dual-view mapper, opt-in only when the app is
  compiled with `EDEN_SPARSE_JIT_DEV=ON` and profiling support. This mapper
  is **not safe for production** until mid-game allocation failures, executable
  aliasing and teardown are validated. The arbitrary 4 GiB limit was removed;
  full demand-driven multi-segment JIT growth is still to be implemented.

**No native build or PS5 execution of these branch changes has taken place.**
See [PS5 architecture and validation gates](docs/PS5_NATIVE_ARCHITECTURE.md).
The currently installed/downloadable application does **not** include these
changes. FC27's input mapping and in-game PlayStation glyph replacement remain
separate outstanding issues.

- Shader worker selection now uses the actual PS5 process CPU-affinity mask
  (not only the machine's advertised logical CPU count). Native performance
  and shader-load timing have not been verified.
- Added lifecycle-specific virtual-vs-committed JIT memory reporting,
  and fixed the uncalled startup memory diagnostic.
- A startup-only RW/RX mapping check can reject the incomplete sparse
  JIT path in a developer build; the production option remains OFF.
- The offline architecture contract check is available at
  `python3 tools/check-ps5-architecture.py` (not a substitute for
  a console build or hardware validation).

**Additional PS5-first JIT work, unqualified:** initial physical sparse
pages now cover Dynarmic's constructor-time constant pool; sparse-reservation
failure uses the dense JIT path; A64 and A32 attempt a one-time cache
evacuation when extension fails before mapping. The installed app still
uses the dense allocator. New physical usage reports distinguish dense
owned direct-memory bytes from sparse reserved/committed bytes, with a
post-destruction leak snapshot. A mocked-kernel host gate is present,
but actual firmware 13.60 JIT aliasing and OOM recovery remain untested.
Do not treat this as an installed or completed dynamic multi-arena JIT.

**Further developer-branch improvements — all games, not title-specific:**
Dynarmic A64/A32 starts can retry smaller code-cache capacities when only
physical allocation fails, preserving real compiler errors. PS5 Vulkan now
initializes persistent per-title guest shader and driver pipeline caches
without blocking on a full shader-rebuild pass or stopping the compiler
worker pool. A driver-cache blob rejected after a RADV update falls back
to a fresh cache. These are **source-only**, not in the installed app;
native PS5 build, shader persistence and gameplay profiling remain necessary.

**PS5-wide robustness fixes (developer branch, not released):** failed
Dynarmic executable-alias mapping no longer returns a non-executable
writable pointer; the generated Dynarmic unit receives its required native
compile definition; Vulkan driver-cache saves now use staged
flush-and-rename transactions, preserving the previous cache on an
interrupted write. All changes are source-level and require native
build/hardware verification before release.

## Changes in Encore R1

Prospero.Eden Encore R1 turns the proven ProsperoEden 1.000.040 base into a PS5 13.60-focused release:

- PS5 firmware **13.60 hardware-tested** as the primary target; Encore reaches the launcher and a current ZBIC title launches successfully.
- ZBIC/zstd NSO support for newer Switch software while retaining LZ4.
- Shipping CPU stability profile uses **Dynarmic per-core JIT**; shared-JIT, successor batching and saved-block compile-ahead stay disabled after the FC 27 freeze investigation.
- Audited Eden fixes are backported without a wholesale rebase: sparse-memory decommit **#4471**, CPU/GPU dirty tracking **#4473**, fence/synchronization cleanup **#4477**, plus reviewed FW23/service/max-session and runtime/HID fixes.
- PS5 OpenGL is built from audited source snapshot **`ad2807d`**: SDK 1.0.1's vertex-buffer lifetime fix plus the reviewed constant-buffer/alignment (`217da45`) and one-time scanout-pool flush (`67c873f`) fixes. RADV/Mesa/PayloadSDK remain on their coherent hardware-qualified 13.60 baseline.
- One storage-root contract: internal defaults to `/data/prosperoeden`; external storage uses the
  exact same `keys/firmware/roms/updates/mods/...` layout under another root.
- The working 0.40 one-shot filesystem helper is hardened with target validation, verified rollback,
  fail-closed postconditions and symlink-safe migration.
- Safe Launch recovery profile without overwriting saved settings.
- Reworked TV-first **Encore launcher UI/UX** with the final Eden Encore neon identity, 4K tropical-night artwork, dark glass surfaces, controller-first navigation and accessibility modes.
- **Nlib rich-media enrichment** for the launcher: cached title metadata, icons, **1080p banners**, gameplay screenshots and local-player capacity, with versioned cache migration and offline fallbacks.
- Four authored video profiles — **Minimum / Recommended / High / Ultra** — plus a derived **Custom** state; profiles are generated from `encore-overrides`, remain title-aware, and keep FSR sharpness conservative by default.
- Global settings reset and per-game override reset now require an explicit second press; mapping reset and shader/JIT cache clearing use the same confirmation rule.
- DualSense-first controls with four profiles (**PlayStation / Switch / Custom PS5 / Custom Switch**), vibration/deadzone controls and multi-controller handling. Automatic menu/gameplay face-button switching was disabled because its heuristic inverted buttons unpredictably; FC27 match mapping is **not yet resolved**. In-game PlayStation glyphs are also not universally supported.
- Diagnostics, bounded caches/logs and safer save import/export.
- Reproducible release packaging with ZIP, optional FFPFSC image and SHA-256 checksums.
- Complete French launcher catalog with **29 packaged language catalogs**, immediate in-app launcher reconstruction for language/font/label changes, release-safe locale detection and hash-verified FTP installation; stale development `language.txt` overrides can no longer force English.
- CodeQL, pinned GitHub Actions, Dependabot and documented security/community policies.

## The big advantages

### 🎯 PS5 13.60 is a first-class target

- **Primary hardware-tested target: PS5 firmware 13.60.**
- Internal storage defaults to **`/data/prosperoeden`** with a fixed folder structure.
- External storage changes only the root; it uses the same required subfolders.
- Encore keeps the 1.000.040 filesystem-access path instead of switching to Lapy.
- No Lapy daemon or Lapy helper dependency is required.
- If the filesystem request is unavailable, Encore stays sandboxed instead of pretending it succeeded.

### 🧩 Newer Switch software support

- Adds **ZBIC / zstd NSO decompression** used by newer Switch software.
- Keeps the existing **LZ4** loader path for older titles.
- Preserves ProsperoEden's PS5 low-memory NSO loading strategy.

### 🛟 Recovery built for a couch / TV emulator

- **Safe Launch** starts one game with conservative settings only for that run:
  - OpenGL
  - Handheld mode
  - 1x internal resolution
  - Bilinear
  - 60 Hz
  - 1080p
  - mods disabled
- Saved settings are **not overwritten**.
- Confirmed **Restore recommended defaults** globally.
- Confirmed **Reset overrides** per game.

### 🎮 DualSense-first UX

- **PlayStation** is the default profile. In the stock profile Encore starts with PS-style menu semantics and can switch to physical Switch face-button positions for sustained gameplay input, with hysteresis when returning to menu/navigation context.
- **Switch** remains a fixed Nintendo-position layout.
- **Custom PS5** and **Custom Switch** stay exactly as mapped by the player and are never changed automatically.
- Global and per-game button mappings are supported.
- Adjustable vibration and stick deadzone.
- Multi-controller hotplug, motion controls and analog triggers retained.
- Launcher input follows the foreground PS5 user.

### ⚙️ Four title-aware video profiles

Encore exposes four authored tiers sourced from `encore-overrides`, plus a derived **Custom** state when manual values no longer match a tier:

- **Minimum** — Vulkan, 1080p, 1x, Bilinear, AA off, 60 Hz.
- **Recommended** — Vulkan, 1440p, 1.25x, Bilinear, **FXAA**, 60 Hz.
- **High** — Vulkan, 2160p, 1.5x, Bicubic, **FXAA**, 60 Hz.
- **Ultra** — Vulkan, 2160p, 2x, Bilinear, AA off, 60 Hz.

A title-specific override may adjust those values without changing the global tier. Manual edits become **Custom** for that scope. Shipping profiles keep the conservative per-core JIT contract; saved-block compile-ahead stays disabled.

### 🧰 Better diagnostics and bounded storage

- Filesystem-access status.
- In the **unreleased local candidate**, diagnostics shows the actual selected Encore storage **root path** rather than pretending that a restricted filesystem view represents the physical PS5 SSD capacity.
- Shader/JIT cache size.
- Log size.
- Safe shader-cache cleanup.
- RADV shader cache capped at **256 MB**.
- Session logs rotate instead of growing forever.
- Cover textures use a bounded LRU cache.

### 🔐 Extra hardening

- Save imports reject **symlink escapes**.
- Settings writes are atomic and invalid JSON falls back safely.
- Package metadata and native dependency closure are validated.
- Optional RADV/Mesa weak imports are resolved only after the real native link.
- Release inputs are pinned and release bundles are reproducible/checksummed.
- Keys, ROM/container files and local save-transfer folders are explicitly ignored by Git.

## Encore vs ProsperoEden upstream

This comparison is against **ProsperoEden v1.000.070**, the current upstream line this fork intentionally does not merge wholesale.

| Area | Prospero.Eden Encore | ProsperoEden v1.000.070 |
| --- | --- | --- |
| Main PS5 target | **13.60 — tested** | Lapy helper validated upstream on **6.02 and 12.70**; other firmware experimental |
| Filesystem model | **Hardened 1.000.040 one-shot access + one internal/external storage-root contract** | Lapy-based exact-title helper / resident-service path |
| Newer NSO compression | **ZBIC + LZ4** | Upstream line evolves independently |
| Recovery | **Safe Launch + global reset + per-game reset** | No equivalent Encore recovery workflow documented |
| Performance UX | **Minimum / Recommended / High / Ultra + Custom**, title-aware via `encore-overrides` | Seven individual performance switches |
| PS5 controls | **PlayStation / Switch / Custom PS5 / Custom Switch**, with PlayStation menu↔gameplay auto-context plus global/per-game mapping | Full button mapping system |
| Diagnostics | **Filesystem mode, free space, cache/log sizes, safe cleanup** | Crash/boot diagnostics and logs |
| Storage hardening | **Bounded RADV cache, rotating logs, bounded cover VRAM** | Shader cache / logging present, different policy |
| Save import safety | **Backup/rollback + symlink rejection** | Save import/export support |
| Updates | **Manual release updates by design** | Built-in network updater |

Encore deliberately chooses **predictability on 13.60** over importing every newer upstream subsystem.

## Firmware compatibility

| PS5 firmware | Encore status |
| --- | --- |
| **13.60** | 🧪 **Primary hardware target — active stability revalidation** |
| Other firmware supported by underlying tooling | ⚠️ **Not validated by Encore yet** |
| Unknown/newer firmware layouts | ❌ **No compatibility claim** |

A firmware having offsets somewhere in the wider PS5 ecosystem does **not** automatically mean Encore has been validated on it.

## Filesystem access and security

Encore uses one storage model:

- default internal root: `/data/prosperoeden`;
- optional external root selected in **Settings → Storage**;
- the same fixed subfolders are used in both cases: `keys/`, `firmware/`, `roms/`,
  `updates/`, `mods/`, `save-import/`, `save-export/` and `ryujinx/`.

Encore keeps the proven ProsperoEden 1.000.040 one-request helper rather than adopting the newer
Lapy path. The helper:

- runs once during single-threaded startup;
- validates the exact Encore title ID `PPSA99008`;
- accepts only the filesystem request used by Encore;
- uses a fixed/versioned protocol and bounded I/O timeouts;
- verifies the resulting state and verifies rollback on failure;
- terminates instead of continuing when the post-request state is inconsistent;
- exits after the one request.

Legacy ProsperoEden data migration is preflighted, symlink-safe and rollback-aware. A pre-existing
external root is preserved instead of being rewritten into a different storage layout.

See [headless/elevation/README.md](headless/elevation/README.md) for implementation details.

## Recommended defaults

See **[SETTINGS.md](SETTINGS.md)** for every exposed setting, defaults, per-game overrides and recommended profiles for 4K/1080p displays and demanding games.

Encore starts conservative:

| Setting | Default |
| --- | --- |
| Renderer | **Vulkan** |
| TV output | **1440p** |
| Internal resolution | **1.25x** |
| Upscaling | **Bilinear** |
| FSR sharpness | **50%** (used only with FSR) |
| Anti-aliasing | **FXAA** |
| Refresh rate | **60 Hz** |
| FPS overlay | **Off** |
| Controller layout | **PlayStation** |
| Stick deadzone | **8%** |
| Vibration | **100%** |
| Console mode | **Docked** |

Try **OpenGL** when a title has a Vulkan-specific issue. Use **0.75x / 0.5x + FSR** when performance is the priority. Higher internal resolutions require substantially more GPU/memory headroom.

## Install

**ZIP is the recommended installation method.** Encore also ships an optional `.ffpfsc` image for
ShadowMountPlus users.

- **ZIP:** extract `PPSA99008` to `/data/homebrew/PPSA99008`.
- **FFPFSC:** mount the release image through a compatible ShadowMountPlus/etaHEN setup.
- **Internal storage:** default root is `/data/prosperoeden`.
- **External storage:** choose another root in Settings → Storage; the folder structure stays identical.

See **[INSTALL.md](INSTALL.md)** for the complete step-by-step guide, update procedure, checksum
verification and troubleshooting.

## Build

Linux is recommended.

```bash
make release
```

Release files are generated under `dist/`.

The GitHub release workflow validates translations, performs the full native build/package pipeline, verifies SHA-256 checksums, and only publishes compiled assets after a successful build.

See [docs/BUILDING.md](docs/BUILDING.md) for toolchain details and [docs/FORK_NOTES.md](docs/FORK_NOTES.md) for the technical audit and validation history.

## Security

Encore uses CodeQL scanning, pinned build inputs, SHA-pinned GitHub Actions, checksummed release
assets, save-import symlink protection, transactional migration checks and a hardened one-shot
filesystem-access path.

Please report exploitable issues privately and avoid publishing proof-of-concept details before a
fix is available. See [SECURITY.md](SECURITY.md) for supported versions, scope and disclosure
instructions.

## What Encore intentionally does not claim

- It does **not** repair PS5 **FPKG entitlement/PPR** support.
- It does **not** make the 13.60 kstuff/FPKG stack reliable.
- It does **not** include keys, firmware, games or copyrighted console data.
- It does **not** silently import the newer Lapy elevation rewrite.
- It does **not** use an automatic renderer fallback that hides real failures.

FPKG/kstuff behavior is a separate jailbreak/runtime concern from the emulator itself.

## Credits

Encore is built from and depends on the work of many upstream projects. The list below covers the
**direct repositories and pinned build/runtime inputs used by Encore**. Each entry identifies
its upstream author, known contributor or project-maintainer account; a project account is not
presented as the sole person who wrote its code. This list is not exhaustive; transitive dependencies of
Eden and the individual licence details are documented in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

### Emulator and launcher foundations

- [ProsperoEden](https://github.com/blackbearreloaded/ProsperoEden) — **Authors / maintainers: BlackBearReloaded (`@blackbearreloaded`)** — original PS5 emulator port/fork Encore is based on.
- [Eden](https://github.com/eden-emulator/mirror) — **Authors / maintainers: Eden Emulator Project team (`@eden-emulator`) and contributors** — emulator core used by Encore.
- [Citron Neo emulator](https://github.com/citron-neo/emulator) — **Authors / maintainers: Citron Neo team (`@citron-neo`); SM/audio fixes by `@HopeSuffers`** — upstream HLE ServiceManager/audio initialization fixes referenced by Encore's **disabled-by-default experimental** backport (not part of the current shipping binary).
- [ProsperoPuzzles](https://github.com/blackbearreloaded/ProsperoPuzzles) — **Authors / maintainers: BlackBearReloaded (`@blackbearreloaded`)** — origin of the launcher drawing/text/animation/sound framework used by Encore.

### PS5 platform, graphics and packaging

- [PS5 Native App Boilerplate](https://github.com/blackbearreloaded/ps5-native-app-boilerplate) — **Authors / maintainers: BlackBearReloaded (`@blackbearreloaded`)** — native runtime, packaging and base platform integration.
- [PS5 OpenGL](https://github.com/blackbearreloaded/ps5-opengl) — **Authors / maintainers: BlackBearReloaded (`@blackbearreloaded`)** — OpenGL 4.6 runtime used by Encore.
- [Mihawk's PS5 Mesa](https://github.com/mihawk-99/PS5_Mesa) — **Authors / maintainers: Mihawk (`@mihawk-99`) and Mesa contributors** — Mesa/RADV source used by the Vulkan path.
- [Mihawk's PS5 Vulkan](https://github.com/mihawk-99/PS5_Vulkan) — **Authors / maintainers: Mihawk (`@mihawk-99`)** — PS5 Vulkan/RADV build and link recipes.
- [Mihawk's PS5 PayloadSDK](https://github.com/mihawk-99/PS5_PayloadSDK) — **Authors / maintainers: Mihawk (`@mihawk-99`) and upstream SDK authors** — PayloadSDK fork used by the RADV toolchain.
- [PS5 Payload SDK](https://github.com/ps5-payload-dev/sdk) — **Authors / maintainers: John Törnblom (`@john-tornblom`) and contributors `@ps5-payload-dev`** — PS5 homebrew SDK used by the native toolchain.
- [ps5-vulkan](https://github.com/mpereiraesaa/ps5-vulkan) — **Authors / maintainers: `@mpereiraesaa` and contributors** — earlier PS5 Vulkan platform work used by the graphics stack.
- [PSBrew/MkPFS](https://github.com/PSBrew/MkPFS) — **Authors / maintainers: PSBrew team (`@PSBrew`)** — optional reproducible `.ffpfsc` image packaging.
- [SharpProspero](https://github.com/SvenGDK/SharpProspero) — **Authors / maintainers: SvenGDK (`@SvenGDK`)** — source/reference used by the native packaging toolchain.

### Compatibility, media, text and build inputs

- [Encore overrides](https://github.com/niakw/encore-overrides) — **Authors / maintainers: `@niakw`** — companion database/source of the four general video tiers, title-specific overrides and the generated PlayStation Auto control profile.
- [ghost-land/Nlib-API](https://github.com/ghost-land/Nlib-API) — **Authors / maintainers: ghost-land team (`@ghost-land`) and contributors** — runtime title metadata and rich launcher media source (icons, 1080p banners, screenshots and local-player metadata).
- [kinnay/zbic](https://github.com/kinnay/zbic) — **Authors / maintainers: `@kinnay`; zstd source files from Atmosphère** — ZBIC/zstd NSO decompression support.
- [FFmpeg](https://github.com/FFmpeg/FFmpeg) — **Authors / maintainers: Fabrice Bellard (original creator), FFmpeg team and contributors** — H.264/VP8/VP9 decoding in the PS5 build.
- [HarfBuzz](https://github.com/harfbuzz/harfbuzz) — **Authors / maintainers: Behdad Esfahbod, David Corbett, Khaled Hosny and HarfBuzz contributors** — shaping for Arabic, Thai and other complex scripts in the launcher.
- [fmt](https://github.com/fmtlib/fmt) — **Authors / maintainers: Victor Zverovich (`@vitaut`) and contributors** — formatting headers used by build/runtime validation paths.
- [LLVM](https://github.com/llvm/llvm-project) — **Authors / maintainers: LLVM community (`@llvm`) and contributors** — compiler-rt pieces used by the PS5 cross build.
- [pacbrew](https://github.com/ps5-payload-dev/pacbrew-repo) — **Authors / maintainers: ps5-payload-dev team and contributors** — pinned PS5 OpenSSL/zlib packages.
- [zlib](https://github.com/madler/zlib) — **Authors / maintainers: Jean-loup Gailly and Mark Adler (`@madler`)** — pinned native dependency used by the PS5 toolchain setup.
- [Boost.Context](https://github.com/boostorg/context) — **Authors / maintainers: Boost.Context team and Boost contributors** — pinned context runtime source used by Eden's PS5 build.
- [Xbyak](https://github.com/herumi/xbyak) — **Authors / maintainers: Mitsunari Shigeo (`@herumi`)** — x86/x64 JIT assembler used by Dynarmic/Eden and adapted by Encore's JIT allocator path.
- [SPIRV-LLVM-Translator](https://github.com/KhronosGroup/SPIRV-LLVM-Translator) — **Authors / maintainers: Khronos Group and SPIRV-LLVM-Translator contributors** — macOS host-toolchain support for the graphics build.
- [stb](https://github.com/nothings/stb) — **Authors / maintainers: Sean T. Barrett (`@nothings`) and authors of stb components** — launcher font baking/system-font loading support.

### PS5 input/audio research reused directly

- [ps5-native-gamepad-input-research](https://github.com/blackbearreloaded/ps5-native-gamepad-input-research) — **Authors / maintainers: BlackBearReloaded (`@blackbearreloaded`)** — native DualSense/gamepad integration reference/code.
- [ps5-audio-decoding-research](https://github.com/blackbearreloaded/ps5-audio-decoding-research) — **Authors / maintainers: BlackBearReloaded (`@blackbearreloaded`)** — native audio integration reference/code.

All credit for the original projects belongs to their respective authors and contributors. Encore's
changes do not imply endorsement by those projects or their maintainers.

## Community

- [Contributing](CONTRIBUTING.md)
- [Support](SUPPORT.md)
- [Code of Conduct](CODE_OF_CONDUCT.md)
- [Security Policy](SECURITY.md)

## License and legal

Prospero.Eden Encore is an **unofficial community fork** distributed under
**GPL-3.0-or-later**. See [LICENSE](LICENSE). Third-party components keep their
own licenses and attribution; the component map is in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and the collected full texts
are in [LICENSES](LICENSES/). Release ZIPs and the installable PS5 title carry
those notices; the standalone `.ffpfsc` therefore keeps a `legal/` directory
inside the installed title.

Encore is not affiliated with, sponsored by, endorsed by, or supported by Sony
Interactive Entertainment, Nintendo, the Eden Emulator Project, or other
upstream projects unless they expressly state otherwise. Product, project and
company names and logos are used only for attribution, compatibility
identification or description of upstream lineage. Copyright licensing does
not itself grant trademark rights.

No encryption keys, Nintendo firmware, commercial games, DLC, updates or other
proprietary console content are included. Use only software and console data
you are lawfully entitled to use.

Nlib is queried at runtime; Encore does not ship a pre-seeded Nlib media
library. Copyright/trademark rights in remote icons, banners, screenshots and
metadata remain with their respective rightsholders. Encore does not claim
that such remote media is public-domain, royalty-free or independently
redistributable.

The launcher SFX are generated locally and deterministically by
`tools/launcher/generate-sfx.py`; no third-party audio samples or external
generative-audio service output is included.

This project is provided **without warranty**, subject to the complete terms in
the applicable licenses.
