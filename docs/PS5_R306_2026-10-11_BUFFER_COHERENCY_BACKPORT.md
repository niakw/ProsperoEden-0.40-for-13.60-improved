> **CORRECTION R307 — le backport Eden #4473/#4477 existait déjà !** Le patch `headless/backports/eden-4473-4477.patch` était appliqué par `tools/apply-eden-backports.sh` et vérifié par `validate_gpu` bien avant R306. Le binaire R306 #38101599715 est vert, mais les 10 ancres étaient déjà en forme corrigée ; R306 n'apporte donc aucun gain de performances démontrable et ajoute une couche redondante. R307 supprime cette couche, préserve le patch original et son reçu SHA-256, et reprend l'audit des vrais points de contention.

# R306 — Cible fluidité 30 FPS / backport Eden #4473 (11 octobre 2026)

## Observation à ne plus perdre

L'utilisateur rapporte **environ 95 % du temps affiché à 30 FPS**, avec pourtant des saccades régulières et une image pixellisée sur FC27. L'outil FPS moyen ne voit ni les sauts ponctuels de temps d'image ni la progression du jeu derrière un frame présenté. **Le critère de succès n'est pas seulement de maintenir 30 FPS** : il faut une cadence régulière, aucune attente bloquante excessive et une sortie visuelle correcte.

Le journal FC27 R302 (133 fenêtres, ~5 s chacune) montre 98 fenêtres ≥29,9 FPS (certaines fenêtres contiennent d'autres scènes, ceci n'est pas un pourcentage du temps *en match*). Parmi elles, 28 fenêtres ont ≥1 000 conflits de cache ; 10 fenêtres ont des frames >38 ms, 7 de celles-là coïncident avec ≥1 000 conflits. À 20,495 FPS (frame 18530), on relevait 18 542 conflits, 320,179 ms d'attente *cumulée entre threads invités*, 0,131 ms d'attente dequeue, et seulement 15,172 ms de compilation JIT en ~5 s. Ces mesures confirment des conflits même près de 30 FPS, sans démontrer le coût de chaque frame ni le lien de causalité d'un conflit individuel.

## Modifications R306

**Port limité de** [Eden #4473](https://github.com/eden-emulator/mirror/commit/dbeb73ee011416cffc6c203945f5ccc6b90621f6), sur le socle Eden épinglé `5f142c79`, et appliqué **uniquement** à la compilation PS5 native avec backend Vulkan, via `headless/eden-buffer-4473.cmake` :

1. `BufferCache::WriteMemory` consulte les intervalles réellement GPU-modifiés (`gpu_modified_ranges`) et non uniquement le suivi des pages, puis marque les écritures CPU. Le vieux chemin pouvait considérer des pages GPU dirty à tort lors de writes.
2. `BufferCache::ObtainCPUBuffer(DiscardWrite)` invalide exactement la région concernée, sans étendre systématiquement aux alignements de 64 octets.
3. `BufferCache::SynchronizeBuffer` découpe les uploads CPU et *exclut* les intervalles dont l'écriture GPU reste propriétaire. Cela vise à éviter de réécrire des données graphiques GPU plus récentes, au prix potentiel d'un coût de recherche d'intervalle supplémentaire ; **aucun bénéfice FPS n'est affirmé sans qualification**.
4. `DmaPusher::Step` restreint le test `IsMemoryDirty` aux blocs Maxwell macro et Kepler inline, et à `min(method_count, header.size)`. La source dérivée PS5 existante est d'abord relue pour **préserver l'arrêt sécurisé** (`system.IsShuttingDown()`) avant application du correctif.
5. `KeplerCompute` capture le drapeau `current_dirty` au moment des uploads, et réévalue ce drapeau au lancement des calculs indirects (source `.cpp` et en-tête synchronisés).

Chaque bloc source est remplacé avec un ancrage exact **une seule fois** ; CMake échoue si l'Eden épinglé change. Le header `buffer_cache.h` et `kepler_compute.h` sont dérivés sous `build/headless/eden4473`, avec include PS5 `BEFORE`. Ni le renderer CPU, ni les mutex `texture_cache/buffer_cache`, ni la PS5 installée, ni les réglages de résolution n'ont été modifiés.

## Validation

- `tools/check-ps5-eden4473.py` : vérifie sélectivité Vulkan, présence des cinq familles de correctifs, préservation du DMA déjà dérivé, et des scénarios d'intervalles GPU-dirty croisés / entièrement dirty / trous CPU / hors zone. Un fixture synthétique ne remplace pas un test de textures FC27.
- Gates host et native : workflows `encore-core-preflight.yml` et `build-040-zbic.yml` exécutent ce contrôle ; une compilation native est obligatoire avant de livrer ce candidat.
- Vérifier les symboles/binary seulement après succès de CI. Ne pas déclarer les saccades / le crash / la pixelisation résolus par ce seul backport.

## Non-choix intentionnels

Aucun `RADV_THREADED_RECORDING=1` automatique, aucun retrait des verrous mémoire, aucune diminution de résolution, aucun merge massif Eden/Mesa/SDK, aucun changement de glyphes/touches/hosts/logs, aucune modification de `fix/0.40-zbic-13.60`. L'objectif immédiat est la *cohérence et la réduction du travail redondant* entre CPU invités et GPU, tout en conservant une image correcte.
