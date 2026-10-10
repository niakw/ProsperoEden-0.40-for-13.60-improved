#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
set -euo pipefail
[[ $# == 0 || ( $# == 1 && ( "$1" == --integration || "$1" == --game ) ) ]]
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
source "$root/tools/host-env.sh"
eden_host_env "$root"
scratch=$(cat "$root/.local/headless-cache")
[[ "$(cd -- "$(cat "$scratch/owner")" && pwd -P)" == "$root" ]]
template="$root/../ps5-native-app-boilerplate"
builder="$root/build/host/ps5-native-tool"
out="$root/build/headless-native"
app="${EDEN_PACKAGE_DIR:-$root/dist/headless/PPSA99008}"
# A separate clean staging directory lets driver candidates omit private game
# assets without deleting or copying the existing development installation.
if [[ -n ${EDEN_PACKAGE_DIR:-} ]]; then
    canonical_root=$(realpath -m "$root")
    canonical_app=$(realpath -m "$app")
    [[ $canonical_app == "$canonical_root"/build/*/PPSA99008 ]] || exit 2
    [[ ${1:-} != --game ]] || exit 2
fi
test -x "$builder"
(cd "$template/runtime" && sha256sum --check --strict libc.prx.sha256)
mkdir -p "$out" "$app/sce_sys" "$app/sce_module"
cp "$scratch/native-local/bin/eden-headless" "$out/llvm-pie.elf"
cp "$scratch/native-local/bin/eden-headless.map" "$out/link.map"
cp "$scratch/native-local/CMakeCache.txt" "$out/CMakeCache.txt"
stub_flags=(--stub-dir "$scratch/sdk/target/lib")
if grep -qx 'EDEN_PS5_OPENGL:BOOL=ON' "$out/CMakeCache.txt"; then
    gl46="$root/.local/ps5-opengl-sdk-ad2807d"
    stub_flags=()
    for stub in "$scratch/sdk/target/lib/"*.so; do
        case "${stub##*/}" in libSceAgc.so|libSceAgcDriver.so) continue ;; esac
        stub_flags+=(--stub "$stub")
    done
    driver_stub="$gl46/lib/libSceAgcDriver.so"
    if grep -qx 'EDEN_PS5_VULKAN:BOOL=ON' "$out/CMakeCache.txt"; then
        driver_stub="$root/build/stubs/libSceAgcDriver.so"
    fi
    stub_flags+=(--stub "$gl46/lib/libSceAgc.so" --stub "$driver_stub")
fi
"$builder" link --in "$out/llvm-pie.elf" --out "$out/eboot.elf" \
    "${stub_flags[@]}" --module-sdk 0x02000009 \
    --companion-sdk 0x08050001 --file-name eboot.elf
"$builder" self --sign --in "$out/eboot.elf" --out "$app/eboot.bin" --magic 0x1D3D154F
cp "$template/runtime/libc.prx" "$app/sce_module/libc.prx"
cp "$root/assets/"{pic0.dds,pic1.dds,snd0.at9} "$app/sce_sys/"
# One Encore raster source feeds both the PS5 tile and the launcher brand.
cp "$root/assets/icon0.png" "$app/sce_sys/icon0.png"
cp "$root/assets/icon0.dds" "$app/sce_sys/icon0.dds"
rm -rf "$app/ui"
cp -a "$root/headless/prosperoeden/ui" "$app/ui"
# Read-only embedded hosts policy. Release must never lose this file.
cp "$root/headless/network-hosts.txt" "$app/network-hosts.txt"
rm -f "$app/ui/art/backdrop.tga" "$app/ui/art/backdrop-blur.tga"
# Keep complete legal notices inside the title itself so a standalone .ffpfsc install never
# separates the binary from the GPL and third-party license texts that accompany it.
rm -rf "$app/legal"
mkdir -p "$app/legal"
cp "$root/LICENSE" "$root/THIRD_PARTY_NOTICES.md" "$app/legal/"
cp -a "$root/LICENSES" "$app/legal/LICENSES"
# Some ShadowMount/package-image install paths preserve ui/lang but drop .po payloads.
# Keep the canonical catalogs and add byte-identical .txt companions; the runtime accepts either.
for catalog in "$app/ui/lang/"*.po; do
    cp "$catalog" "${catalog%.po}.txt"
done
if command -v magick >/dev/null 2>&1; then
    image_convert=(magick)
elif command -v convert >/dev/null 2>&1; then
    image_convert=(convert)
else
    echo "ImageMagick (magick or convert) is required to build Encore launcher art" >&2
    exit 2
fi
# One canonical Eden background is reused for the PS5 shell art, launcher and in-game loading
# screen. 1080p is enough for the launcher/loading texture while keeping its transient VRAM cost
# small; the PS5 home-screen DDS stays native 4K.
"${image_convert[@]}" "$root/assets/encore-background.jpg" -resize '1920x1080^' -gravity center -extent 1920x1080 \
    -flip -alpha off -define tga:bits-per-pixel=24 -compress None "$app/ui/art/backdrop.tga"
python3 - "$app/ui/art/backdrop.tga" <<'PY2'
import pathlib, sys
data = pathlib.Path(sys.argv[1]).read_bytes()
if len(data) != 18 + 1920 * 1080 * 3 or data[1] != 0 or data[2] != 2 or data[16] != 24:
    raise SystemExit("Generated Encore backdrop.tga is not 1920x1080 uncompressed true-colour TGA")
PY2
# OpenGL's launcher texture convention is vertically opposite ImageMagick's TGA output.
# Flip only the generated launcher texture; the canonical PNG/PS5 tile remains untouched.
"${image_convert[@]}" "$app/sce_sys/icon0.png" -resize 256x256 -flip -alpha on \
    -define tga:bits-per-pixel=32 -compress None "$app/ui/art/brand.tga"
python3 - "$app/ui/art/brand.tga" <<'PY'
import pathlib, sys
data = pathlib.Path(sys.argv[1]).read_bytes()
if len(data) < 18 or data[1] != 0 or data[2] != 2 or data[16] not in (24, 32):
    raise SystemExit("Generated Encore brand.tga is not an uncompressed true-colour TGA")
PY
# Filesystem access helper (headless/elevation, built for PPSA99008): elfldr runs it at startup.
make -s -C "$root/headless/elevation/helper" OUTPUT="$root/build/elevation/sandbox-elevator.elf" \
    PS5_PAYLOAD_SDK="${PS5_ELEVATION_SDK:-/opt/ps5-payload-sdk}"
python3 "$root/headless/elevation/validate-helper.py" "$root/build/elevation/sandbox-elevator.elf"
cp "$root/build/elevation/sandbox-elevator.elf" "$app/sandbox-elevator.elf"
python3 - "$root" "$template" "$app" "${1:-}" <<'PY'
import json, pathlib, runpy, shutil, sys
root, template, app = map(pathlib.Path, sys.argv[1:4])
game = sys.argv[4] == '--game'
integration = sys.argv[4] in ('--integration', '--game')
if game:
    assert (app / 'game-assets.json').is_file()
    assert (app / 'assets/keys/prod.keys').is_file()
value = json.loads((template / 'sce_sys/param.json').read_text())
value.update(titleId='PPSA99008', conceptId='99008', contentId='UP9000-PPSA99008_00-PROSPEROEDEN0001')
# The app version has one home: the launcher shows the same value.
import re
value['contentVersion'] = re.search(r'kPackageVersion = "([0-9.]+)"',
    (root / 'headless/prosperoeden/version.h').read_text()).group(1)
value['localizedParameters']['en-US']['titleName'] = 'Prospero.Eden Encore'
value['pubtools']['loudnessSnd0'] = '-28.00'
# The console gives a 120 Hz output (Settings > Video, headless/display_refresh.h) only to a title
# that declares it. Declaring it changes nothing by itself: the output stays at 60 Hz until asked.
value['attribute3'] = int(value['attribute3']) | 0x80040
(app / 'sce_sys/param.json').write_text(json.dumps(value, indent=2) + '\n')
runpy.run_path(str(root / 'tools/load_alignment.py'))['check_load_alignment']((app / 'eboot.bin').read_bytes())
profile = (root / 'build/headless-native/CMakeCache.txt').read_text()
development = 'EDEN_DEV_PROFILE:BOOL=ON' in profile
if not development:
    assert 'EDEN_SHARED_JIT:BOOL=OFF' in profile
    assert 'EDEN_JIT_COMPILE_BATCH:BOOL=OFF' in profile
assert sum(profile.count('EDEN_DEVICE_FRONTEND:BOOL=' + v) for v in ('ON', 'OFF')) == 1
devices = 'EDEN_DEVICE_FRONTEND:BOOL=ON' in profile
graphics = 'EDEN_PS5_OPENGL:BOOL=ON' in profile
assert not (integration and devices)
assert not game or graphics
fixture_name = 'core-integration.nro' if integration else 'core-devices.nro' if devices else 'core-homebrew.nro'
shutil.copy2(root / 'build/fixture' / fixture_name, app / 'core-homebrew.nro')
(root / 'build/headless-native/frontend.json').write_text(json.dumps({
    'devices': devices,
    'gpu_probe': 'EDEN_GPU_PROBE:BOOL=ON' in profile,
    'renderer': 'opengl-4.6-compatibility' if graphics else 'null', 'guest_fixture': 'retail-game' if game else 'cpu-state-memory-atomics-fp-simd-services' if integration else 'timer-sync-service-storage-hid-audio-renderer-voice-mix-src-high' if devices else 'timer-sync-service-storage',
    'vulkan': 'EDEN_PS5_VULKAN:BOOL=ON' in profile,
    'vulkan_driver': 'RADV' if 'EDEN_VULKAN_DRIVER:STRING=RADV' in profile else 'CUSTOM',
    'development_backend': 'Vulkan' if 'EDEN_DEV_VULKAN:BOOL=ON' in profile else 'user-preference',
    'development_rom_id': next((line.split('=', 1)[1] for line in profile.splitlines()
                                if line.startswith('EDEN_DEV_ROM_ID:STRING=')), ''),
    'hardware_qualified': False,
}, indent=2) + '\n')
PY
llvm-readobj-18 --dyn-symbols --needed-libs "$out/llvm-pie.elf" > "$out/imports.txt"
"$builder" self --inspect --file "$app/eboot.bin" > "$out/fself-inspection.txt"
sha256sum "$app/eboot.bin" "$app/core-homebrew.nro" "$app/sce_module/libc.prx" \
    "$app/sce_sys/param.json" "$app/sce_sys/icon0.png" "$app/sce_sys/icon0.dds" "$app/sce_sys/pic0.dds" "$app/sce_sys/pic1.dds" \
    "$app/sce_sys/snd0.at9"
