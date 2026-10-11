> **Rectificatif R307 :** la comparaison directe avec Eden 5f142c79 ne décrivait pas toutes les modifications effectivement compilées. Notre script `tools/apply-eden-backports.sh` applique **déjà les correctifs #4473 ET #4477** via `headless/backports/eden-4473-4477.patch`. Ils ne constituent donc pas de nouvelles optimisations à intégrer. R306 a démontré cette duplication sur la console CI et R307 a retiré son overlay. La contention de `RasterizerVulkan::PrepareDraw` reste à optimiser au-delà de ces correctifs.

# R305 — Audit des interfaces CPU / caches / Vulkan / PS5 (11 octobre 2026)

## Périmètre et sources

Audit **en lecture seule des anciens journaux console** `crash-20261011-020422-heap.log`, `crash-20261011-020422-eden_log.txt`, `crash-20261011-020422.txt` et des traces antérieures FC27, disponibles via le FTP autorisé du Mac. Pas de manipulation console, ni de reproduction demandée à l'utilisateur.

Version de base : `niakw/Prospero.Eden-Encore` branche `dev/ps5-sparse-jit` R304 (PS5 CI #38098982583 : SUCCESS). Source épinglée **Eden** `5f142c7926d0c7fcbbd0ce30794d72f638a43b2a`; pilote **PS5_Vulkan** `3f3ee69607013b345d2baa6d6a37c86745649a08`; **PS5_Mesa** `0b2d6d1a61d9bbf89cf8beb88a696144f67c61f8`; **PS5_PayloadSDK** `95c08f27386fc698f6bbe21dde3030140a41d10b` : `tools/deps.json`.

Comparaison des dépôts upstream consultés : Eden master `67bada77`, ProsperoEden main `351057fa`, PS5_Mesa main `47e9eb61`, PS5_Vulkan main `252bf912`, PS5_PayloadSDK main `b5efad52`. **Ne pas faire de merge général :** plus de 76 commits Eden, transformations de fichiers source à ancres exactes, divergences des dépôts PS5. Tester les backports individuellement.

## Chaîne réelle de l'image

```text
FC27 Switch (guest A64) -> Dynarmic JIT (3 cœurs invités très actifs)
    -> Core::Memory / SparseLargeVector / pages surveillées GPU
    -> Core::GPU::OnCPUWrite / invalidation / GPU thread sync
    -> RasterizerVulkan::OnCPUWrite/GetFlushArea (buffer_cache/texture_cache mutex)
    -> Vulkan BufferCache / TextureCache / PipelineCache / scheduler
    -> RADV (PS5_Mesa, ACO, winsys AGC + VideoOut via PS5_Vulkan)
    -> PresentManager / frame pacing -> écran 4K
          ^
    PS5 SDK: CPU scheduling, pthread mutex/TLS, heap et mémoire GDDR6 partagée
```

Un verrou contentionné dans le cache graphique **peut gêner plusieurs CPU invités alors même que le compteur d'images présentées affiche 30 FPS**, car le jeu et l'affichage ne sont pas des étapes identiques.

## Ce que prouvent les journaux R302 — NE PAS confondre FPS et fluidité

133 fenêtres instrumentées d'environ 5 s, rapprochées entre `EDEN_VULKAN_FRAME` et `EDEN_FRAME_PRESSURE` (attention : deux flux de mesure doivent porter un même compteur de frame avant toute attribution stricte).

- **98 fenêtres ≥ 29,9 FPS** ; **28/98** ont ≥ 1 000 échecs de `try_lock` du cache graphique, et **5/98** contiennent une image > 50 ms. Une moyenne à 30 FPS ne démontre pas la régularité temporelle du jeu, et la mesure ne certifie pas que le contenu invité a progressé à chaque présentation.
- À FPS ≥ 29,95 (92 fenêtres), le nombre d'échecs `try_lock` est **24–2 335**, médiane **628** ; le temps d'attente bloqué cumulé est **0,19–68,92 ms / 5 s**, médiane **31,52 ms**. Il y a donc déjà des **conflits nombreux sans perte de moyenne FPS**.
- Entre 20 et 25 FPS (14 fenêtres), médiane **3 272,5** conflits (extrême **18 542**) et temps d'attente cumulé médian **78,75 ms / 5 s** (extrême **320,18 ms**). **12/14** ont au moins 1 000 conflits. **Corrélation forte** avec le ralentissement, **mais pas preuve que la somme des attentes seules explique la baisse**.
- Parmi les 20 fenêtres < 25 FPS, **2** comportent moins de 1 000 conflits : plusieurs mécanismes coexistent. Un total de 60 ms d'attente réparti uniformément n'a pas le même effet que 60 ms concentrées sur une seule image.
- En fin de match, 30 FPS avec `guest_dequeue_ms≈0,8–1,1 s/5s` et `gpu_full_ms≈0` bascule vers ~20 FPS avec `guest_dequeue_ms≈0,1 ms/5s`, `gpu_full_ms≈46–187 ms/5s` et jusqu'à **18 542** contentions. Ce contraste indique que les trames de jeu cessent d'être prêtes assez vite, plutôt qu'une saturation continue de la file GPU.
- Le JIT n'est presque plus en compilation pendant certaines fenêtres lentes (`jit_ms≈9–105` sur 5 s), mais **les gels distincts de plusieurs secondes** peuvent joindre forte compilation JIT + file GPU pleine (5 366 ms d'image, 4 583 ms GPU producer full). **Deux problèmes**, pas un unique cache insuffisant.
- Le **GPU physique** n'a pas de métrique d'occupation établie par `gpu_idle_ms` : c'est le temps d'attente du *thread logiciel* GPU, à ne jamais présenter comme « GPU PS5 libre à 80 % ».

### Caveat instrumental majeur

`headless/performance.h::GuestCacheLock` mesure ses conflits par `mutex.try_lock()` puis incrément d'atomiques **uniquement avec Detailed Logging** ; sans diagnostics il appelle directement `mutex.lock()` sans les atomiques. Les comptes historiques rendent observable la contention, mais les mesures à 30 FPS n'établissent pas le coût micro-stutter **par image** ni le même coût avec logs désactivés. Un nombre d'échecs ne mesure pas la durée, et le coût de instrumentation peut ajouter à la contention observée. Prioriser analyse des temps et distribution temporelle, sans supprimer les locks de cohérence mémoire.

## Audit comparatif des interfaces et dépendances

| Interface | Code Eden/Encore réellement concerné | Différence vérifiée dans le dépôt upstream | Verdict / action |
|---|---|---|---|
| **Dynarmic JIT A64 ↔ mémoire invitée** | `headless/CMakeLists.txt` dérive émetteurs, `src/memory_pages.cpp`, `headless/checked-fastmem.cmake` couvre A32 seulement | Eden master comporte corrections SparseLargeVector #4471 ; ProsperoEden #104 adapte aussi les variables `HostPageBits/HostPageMask` **à la version Eden 67bada77** | **P1** inspecter la durée de gestion des pages et l'absence de corruption. Ne PAS copier la modification #104 telle quelle : notre Eden épinglé utilise des `const` ordinaires, pas les mêmes `inline const`. Déjà R304 : limiter uniquement les erreurs console. |
| **CPU guest ↔ GPU buffer/texture** | `RasterizerVulkan::PrepareDraw` protège le couple `buffer_cache.mutex + texture_cache.mutex` durant `pipeline->Configure` et le draw. `OnCPUWrite` et `GetFlushArea` prennent ces verrous depuis les cœurs invités | Eden #4473 corrige `BufferCache::WriteMemory`, dirty tracking Maxwell/Kepler et les CPU buffers ; #4477 révise fences/lecture GPU ; #4490 ajoute le maintien des écritures GPU lors d'une invalidation NCE | **P0** premier suspect pour micro-saccades FC27, mais ne pas retirer les locks, inventer une stratégie de spin/fairness ni backporter #4477+4490 sans leurs nouveaux contrats. Backport #4473 **ciblé** après comparaison de toutes ses unités et contrôles de cohérence. #4490 concerne spécifiquement NCE et n'est **pas une preuve de bénéfice pour Dynarmic/PS5**. |
| **GPU queue ↔ Vulkan scheduler** | `tools/prepare-vulkan-port.py` limite le buffer à 512 draws (correctif ProsperoEden #102) et la cadence via `dispatch_mask` ; `gpu_full_ms` signale l'engorgement ponctuel | ProsperoEden #102 est déjà intégré à R302 ; latest #104 adapte Eden, non un correctif spécifique de FC27 | **P1** ne pas revenir à 4096 (risque `VK_ERROR_DEVICE_LOST`), ni changer arbitrairement la taille de la file. Bien séparer gels extrêmes des ralentissements continus. |
| **PS5 RADV / Mesa ↔ enregistrement Vulkan** | `PS5_Mesa` épinglée à `0b2d6d1a`, `PS5_Vulkan` à `3f3ee696` | Mesa `d0d7325e` ajoute un worker de recording optionnel (`RADV_THREADED_RECORDING=1`), avec corrections de lifecycle ultérieures ; Mesa `47e9eb61` met à jour le mode VideoOut ; nouveau PS5_Vulkan `252bf912` pointe sur cette Mesa | **P1/P2** candidate isolée, **OFF par défaut**, pas une correction établie des mutex `RasterizerVulkan` (qui sont en amont du driver). Risque de complexité et d'attentes supplémentaires si activée sans test de cohérence. |
| **SDK pthread / heap / CPU** | allocations multi-thread, mspace, JIT et caches, appel `pthread_getspecific` visible dans le crash non entièrement symbolisé | SDK `3752be7e` abandonne les spin-waits dans dlmalloc (`USE_SPIN_LOCKS=0`) et remplace l'attente active d'initialisation par `nanosleep`; commits plus récents règlent fichiers/Lapy | **P1** candidate stabilité/ordonnancement ; ne corrige PAS les mutex propres aux caches Eden. Conserver les APIs Sony et garanties de `malloc/free` avant toute migration ; ABI/CI séparées. |
| **Image guest → scale → VideoOut PS5** | `headless/display_refresh.h`, presets / paramètres par jeu, Vulkan filter/presenter | Eden #4503 contient un contournement de shaders fragment problématiques pour pilotes non NVIDIA, qui **saute des shaders** : risque d'objets/effets absents ; VideoOut Mesa a ses propres corrections récents | **P1 qualité** vérifier rescaling et format des textures, ordre de passage FXAA/filtre, image source puis upscale 4K ; **ne pas activer** un shader-skip global pour « corriger » une pixelisation. |
| **Journaux / crash / mémoire** | `Core::Memory::Read/Write` rapportaient les 38 472 invalid guest accesses en ~1,07 s ; `headless/performance.h`, `headless/crash_report.cpp` | R304 Encore corrige la tempête de lignes sans changer les comportements d'accès mémoire, total conservé sans logs | **Corrigé source+build PS5 vert** ; cela ne suffit pas aux ralentissements permanents de FC27. Vérifier la raison des accès invalides indépendamment de leur nombre de logs. |

## Séquence de résolution proposée — sans autre test demandé à l'utilisateur

1. **Verrous** : établir quelle portion de `PrepareDraw/Configure`, `OnCPUWrite`, `GetFlushArea` élargit les sections critiques. Toute modification doit garder la cohérence des buffers/texture/shader et l'ordre des verrous ; comparaison de la paire Eden épinglé / #4473 avant backport.
2. **Code pilote** : isoler le nouveau RADV recording au niveau du **pilote**, pas des mutex Eden, et vérifier les garanties de fin de commande Vulkan et ses threads. Ne pas basculer le driver global dans une release sans validation matérielle.
3. **SDK** : vérifier la compatibilité de `USE_SPIN_LOCKS=0` et des nouveaux points d'attente avec les allocateurs d'Encore, sans modifier les FPS/qualité.
4. **Image** : effectuer un audit fonctionnel de la séquence guest resolution → texture cache → pipeline → filtre → VideoOut ; l'utilisateur a testé d'abord **1440p / 1×**, ensuite d'autres réglages. Le réglage actuel d'un ancien relevé (`2160p / 1,25×` par jeu) **n'est pas un réglage immuable**.
5. **Conserver les deux cibles distinctes** : temps d'image régulier (même quand la moyenne reste 30), et suppression des gros blocages/crashes.

## Source links

- [Eden source épinglée](https://github.com/eden-emulator/mirror/tree/5f142c7926d0c7fcbbd0ce30794d72f638a43b2a)
- [Eden #4473 CPU buffer / Maxwell/Kepler](https://github.com/eden-emulator/mirror/commit/dbeb73ee011416cffc6c203945f5ccc6b90621f6)
- [Eden #4477 fence synchronization](https://github.com/eden-emulator/mirror/commit/f273423b2b83f1a37cc7c1a7a92601f26e0c12ae)
- [Eden #4490 NCE invalidation](https://github.com/eden-emulator/mirror/commit/8e2d26c272681d6cafe6d5e703dafdc8200c7b65)
- [ProsperoEden #104 nouveau socle](https://github.com/blackbearreloaded/ProsperoEden/commit/351057fac07d76596afd2d109e9c6e5a3879dede)
- [Mesa threaded recorder optionnel](https://github.com/mihawk-99/PS5_Mesa/commit/d0d7325e447bb7872583298643e82a2a284c6412)
- [SDK heap contention](https://github.com/mihawk-99/PS5_PayloadSDK/commit/3752be7e7812713e01fbe998d92952cd7b559f7f)
- [R304 PS5 CI](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38098982583)

## Hot-path code trace: why there are lock conflicts even at 30 FPS

Exact call-site verification in pinned `eden-emulator/mirror@5f142c79` (not inferred from a GPU utilization graph):

1. `src/video_core/renderer_vulkan/vk_rasterizer.cpp::RasterizerVulkan::PrepareDraw` calls `pipeline_cache.CurrentGraphicsPipeline()` **before** the paired locks (shader/pipeline creation can thus produce a separate slow path).
2. It then takes **both** `buffer_cache.mutex` and `texture_cache.mutex` with `std::scoped_lock`. Within this critical section it calls `pipeline->Configure(is_indexed)`, `UpdateDynamicStates()`, and the draw-submission callback.
3. In `src/video_core/renderer_vulkan/vk_graphics_pipeline.cpp::GraphicsPipeline::ConfigureImpl`, that critical section can include `texture_cache.SynchronizeDescriptors(false)`, staging uniform/storage buffers, texture sampler lookups, `FillImageViews`, descriptor updates and allocation. More geometry/textures or CPU→GPU page changes increase how often/long this region executes. **This is a concrete shared chokepoint, not proof of which nested function consumes the extra time.**
4. Guest CPU threads concurrently enter `RasterizerVulkan::OnCPUWrite` and `GetFlushArea`, which request the same `buffer_cache` or `texture_cache` mutex. Repeated guest writes or tracked-page invalidations can therefore stall CPU threads while the GPU worker configures draws.
5. At ~20.5 FPS (frame 18530), `cache_contended=18542` and `cache_wait_ms=320.179` across the 5 s window; at 30 FPS (frame 17237), `cache_contended=997` and `cache_wait_ms=48.571`. The **~6.6× increase in measured blocked milliseconds** and **~18.6× increase in failed try_lock attempts** accompany the scene's slowdown. The 320 ms sum across multiple CPU threads still does NOT fully account for losing ~50 frames/5 s: host JIT execution cost, work *inside* each lock, GPU draws and scheduling remain relevant.

**Unsafe shortcut to reject:** taking one lock for the full guest frame, bypassing `OnCPUWrite`/flush or shortening a critical section without transferring ownership/coherence can cause missing textures, corrupted rendering and GPU faults, exactly what must be avoided. The correct next code change needs a contract for each `ConfigureImpl` cache operation and whether it can run safely before/after a lock; prefer adapting vetted upstream changes to making up a new synchronization model.

## Reproducible analysis tool (R305)

`tools/analyze-ps5-cache-contention.py` now groups near-30 and below-25 windows **without declaring 30 FPS smooth**, and pairs `EDEN_FRAME_PRESSURE` with `EDEN_VULKAN_FRAME` only when their `frame`/`total` values match. `tools/check-ps5-frame-window-analysis.py` runs synthetic cases including 1 000+ conflicts while 30 FPS, a late frame without an FPS drop, and deliberately mismatched image IDs. No local log copy, no change on Mac or console.

**CI scope:** the R305 parser regression is a host-only correctness gate; no R305 PS5 binary has been compiled. The earlier R304 native image has already passed PS5 build #38098982583. Runtime speed/graphics quality are not certified by an audit or CI run.


## R308 — comparaison des forks PS5, décision de portage

Audit en lecture seule après le build natif expérimental R307 [#38103076311](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38103076311) (**SUCCESS**, source `5d5fc190`). Les forks comparés utilisent la **même source Eden épinglée** `5f142c79` ; ne pas confondre leur annonce de performances avec une amélioration prouvée sur FC27.

| Source comparée | Mécanisme réel | Présence dans Encore | Décision |
| --- | --- | --- | --- |
| [Tiang-88/ProsperoEden0](https://github.com/Tiang-88/ProsperoEden0) | `dispatch_mask` paramétrable, attente instrumentée des mutex invités ; fork rapporte moins de ralentissements lors d'une scène lourde avec un dispatch par lots | **Déjà présent** : `GuestCacheLock`, `dispatch_mask` par défaut **7** (1 transfert de travail toutes les 8 commandes concernées), suivi `EDEN_FRAME_PRESSURE`. Notre limite `DRAWS_TO_DISPATCH` est **512**, contre 4096 dans le fork antérieur | **Ne pas réappliquer** le code existant et surtout ne pas relever la limite à 4096 : le correctif PS5/ProsperoEden #102 l'a réduite pour éviter `VK_ERROR_DEVICE_LOST`. Le gain revendiqué chez Tiang ne qualifie pas le compromis spécifique de notre pilote |
| [mihawk-99/PS5_ProsperoEden](https://github.com/mihawk-99/PS5_ProsperoEden) | `fast_first_pipelines`: créer d'abord une pipeline Vulkan non optimisée, reconstruire ensuite une version optimisée dans un `ThreadWorker(2)`, publier via `optimized_ready` release/acquire | **Absent** d'Encore. `vk_graphics_pipeline_cost.cpp` suit encore le chemin classique ; `dev_vulkan.h` n'a pas `fast_first_pipelines` | **Candidate isolée pour les premiers effets** : le fork rapporte 32 % de temps d'attente en moins sur les nouveaux pipelines dans un autre titre, pas 32 % de FPS et pas une correction des verrous `PrepareDraw`. Nécessite une nouvelle définition de `GraphicsPipeline` (en-tête généré), la recompilation de tous les consommateurs, une gestion de destruction/worker vérifiée et le contrôle strict des artefacts ccache |
| [PS5_Vulkan/Mesa](https://github.com/mihawk-99/PS5_Vulkan) | Driver RADV et file de soumissions Vulkan | Pins et réglages indépendants du cœur Eden. PS5_Mesa `0b2d6d1` est déjà utilisé dans notre audit, mais les évolutions du driver ne réduisent pas mécaniquement un mutex d'Eden | Pas de saut de driver sur la seule foi d'une mesure GPU d'un autre jeu ; garder le lien entre PS5_Vulkan, Mesa, SDK et ABI |

**Vérification d'équivalence R306 → R307 :** R306 compilait deux sources CMake `eden4473/dma_pusher.cpp` et `eden4473/kepler_compute.cpp`, retirées en R307 (153 unités contre 155). Le patch `headless/backports/eden-4473-4477.patch` reste appliqué par `tools/apply-eden-backports.sh`, validé au build natif. En parallèle, `headless/CMakeLists.txt` **continue** de produire `dma_pusher.cpp` dérivé avec l'attente d'arrêt `system.IsShuttingDown()` ; le correctif de sortie n'est pas abandonné. SHA256 de `eboot.bin` R306 `23c4e4b5…`, R307 `8885c573…`, tous deux à 71 893 593 octets : différence binaire constatée, ni équivalence bit-à-bit ni gain FPS affirmés.

**Chaîne causale prioritaire FC27 :** au lieu d'optimiser à l'aveugle le cache, suivre `RasterizerVulkan::PrepareDraw` → double lock `buffer_cache/texture_cache` → `GraphicsPipeline::ConfigureImpl` (synchronisation de descripteurs, `FillImageViews`, index/texture buffers) → `OnCPUWrite/GetFlushArea` côté cœurs invités → file GPU/swapchain. Les logs historiques établissent une contention récurrente à ~30 FPS et une corrélation renforcée durant les baisses, mais ne donnent pas la décomposition temporelle à l'intérieur de `ConfigureImpl`. Rejeter comme « optimisation » tout contournement du mutex, de l'écriture GPU, de `runtime.Finish()` et des fences sans contrat de possession/visibilité. Les gros gels JIT+queue GPU restent un problème distinct.

**Priorité suivante :** identifier une modification *petite, vérifiable et indépendante* réduisant le travail sous les deux verrous, avec preuve que chaque lecture/écriture de texture/buffer reste protégée et tests de cohérence ; ne pas importer les en-têtes ABI `GraphicsPipeline` de Mihawk ni activer un nouveau thread de pipelines dans le R307 validé. Ces travaux ne doivent pas nécessiter d'autre test demandé à l'utilisateur tant que les anciens journaux restent exploitables.


## R309 — GPU batch threshold: native hard ceiling + isolated 64-draw A/B

**Actual native code fix** in `tools/prepare-vulkan-port.py` (exact-source pinned rewrite of `RasterizerVulkan::FlushWork`): original Eden checked `(++draw_counter & CHECK_MASK) == CHECK_MASK` before checking `draw_counter < DRAWS_TO_DISPATCH`. For `DRAWS_TO_DISPATCH=512`, that allows a hard flush at **519 drawings for 8-draw cadence**, **575 drawings for 64-draw cadence**, and **1023 at 512-draw cadence**, rather than at 512. R309 increments the counter, flushes **immediately at count >=512** and resets to zero; only otherwise considers dispatching on the selected mask. All `Scheduler` work and fences remain intact; nothing skips or fakes image output.

- Shipping default and users' normal profiles: **8-draw dispatch cadence unchanged** (`headless/performance.h` starts `dispatch_mask=7`).
- PS5 experimental **EDEN_DEV_PROFILE**: batch **64** (`main.cpp` resets `dispatch_mask=63` per title), motivated by [Tiang's PS5 fork](https://github.com/Tiang-88/ProsperoEden0) whose 64-draw batching reduced software worker pressure on a different game. **Not claimed to improve FC27** without real PS5 timings.
- Optional experimental `dev-settings.txt`: `dispatch_draws=8` restores 8, or `16,32,64,128,256,512` for per-title A/B. The strict 512-draw flush ceiling applies to all masks. No guest memory synchronization, lock ownership, Vulkan barriers, graphics settings or shipping binaries changed.
- New `tools/check-ps5-vulkan-dispatch-ceiling.py` extracts the **exact generated C++** replacement from the Python source generator using AST, compiles it under clang++/g++ and executes 2,048 draw events at each 8/16/32/64/128/256/512 cadence. Checks count never reaches 512 after a draw, exactly 4 flushes, precisely expected handoffs, and the shipping/dev reset + user override contracts. Added to host core-preflight and full native build startup checks.
- Risk: 64 instead of 8 may raise queue handoff latency or reduce responsiveness despite lowering scheduling overhead. Remains restricted to dev All-On; cannot assert no stutters or no pixelation without a PS5 run. R307 native build [#38103076311](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38103076311) is the reference baseline, not an R309 performance measurement.

 
## R309 native result and R310 image-chain lead

- **R309 native PASS:** [workflow #38104316298](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38104316298), source `0c0c73be`. Actual PS5 `vulkan_rasterizer.cpp.o` rebuilt and linked, `tools/check-ps5-vulkan-dispatch-ceiling.py` PASS for all seven draw cadences, GPU #4473/#4477 PASS; staged package 164 files PASS. All-On test app [artifact 11689485381](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38104316298/artifacts/11689485381), symbols [11689415531](https://github.com/niakw/Prospero.Eden-Encore/actions/runs/38104316298/artifacts/11689415531). Release skipped; PS5 runtime FPS/stutter/output pixels **not** verified. Revert experimental 64-draw cadence to 8 via `dev-settings.txt dispatch_draws=8`; do not touch #4473 memory coherency or synchronization fences.
- **Image chain:** `headless/main.cpp` controls `Settings::resolution_setup` (guest internal 1×/1.5× etc), `scaling_filter` (FSR/bicubic/nearest), and independently `Eden::Display::output_width/output_height` (1920×1080/2560×1440/3840×2160). `headless/display_refresh.h` defines a fixed 3840×2160 Vulkan driver output when the selected renderer frame size is smaller. In pinned Eden `vk_present_manager.cpp::CopyToSwapchainImpl`, differing frame vs swapchain sizes cause `cmdbuf.BlitImage(...,VK_FILTER_LINEAR)` when blit is supported, or a bounded `CopyImage` otherwise. A 1440p video output to 4K therefore **can incur second bilinear resampling** after FSR; this may lose sharpness, but is **not demonstrated** to be the sole cause of pixelation at other settings. Before any R310 visual fix, inspect actual guest framebuffer, filter, final VkExtent and display mode; do not silently force 4K or sacrifice high-FPS settings.
