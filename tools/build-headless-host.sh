#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
base_path=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
darwin_zlib_include=
darwin_zlib_library=
darwin_icu_root=
if [[ $(uname -s) == Darwin && -d /opt/homebrew/opt/llvm@18/bin ]]; then
    shim="$root/.local/llvm18-bin"
    mkdir -p "$shim"
    for tool in clang++ ld.lld llvm-ar llvm-ranlib llvm-nm llvm-readobj llvm-objcopy; do
        [[ -x /opt/homebrew/opt/llvm@18/bin/$tool ]] || continue
        ln -sf "/opt/homebrew/opt/llvm@18/bin/$tool" "$shim/${tool}-18"
    done
    export PATH="$shim:/opt/homebrew/opt/llvm@18/bin:/opt/homebrew/bin:/opt/homebrew/sbin:$base_path"
    [[ -d /opt/homebrew/opt/zlib/include ]] && darwin_zlib_include=-DZLIB_INCLUDE_DIR=/opt/homebrew/opt/zlib/include
    [[ -f /opt/homebrew/opt/zlib/lib/libz.dylib ]] && darwin_zlib_library=-DZLIB_LIBRARY=/opt/homebrew/opt/zlib/lib/libz.dylib
    [[ -d /opt/homebrew/opt/icu4c@78 ]] && darwin_icu_root=-DICU_ROOT=/opt/homebrew/opt/icu4c@78
else
    export PATH="$base_path"
fi
cd "$root"
mkdir -p .local build/headless-host build/fixture
bash tools/build-core-fixture.sh
# Thousands of dependency files and compiler checks are slow across /mnt/c.
cache_parent="${XDG_CACHE_HOME:-$HOME/.cache}"
if [[ ! -f .local/headless-cache ]] || [[ ! -d "$(cat .local/headless-cache)" ]]; then
    mkdir -p "$cache_parent"
    scratch=$(mktemp -d "$cache_parent/ps5-eden-headless.XXXXXX")
    printf '%s\n' "$root" > "$scratch/owner"
    printf '%s\n' "$scratch" > .local/headless-cache
fi
scratch=$(cat .local/headless-cache)
[[ "$scratch" == "$cache_parent"/ps5-eden-headless.* && "$(cd -- "$(cat "$scratch/owner")" && pwd -P)" == "$root" ]]
eden="$scratch/source"
if [[ ! -f "$eden/CMakeLists.txt" ]]; then
    python3 - <<'PY'
import hashlib, json, pathlib
p = pathlib.Path('.deps/eden-5f142c79.tar.gz')
assert hashlib.sha256(p.read_bytes()).hexdigest() == json.loads(pathlib.Path('UPSTREAM.json').read_text())['archives'][p.name]
PY
    mkdir -p "$eden"
    tar -xzf .deps/eden-5f142c79.tar.gz --strip-components=1 -C "$eden"
fi
printf '%s\n' '5f142c7926d0c7fcbbd0ce30794d72f638a43b2a' > "$eden/GIT-COMMIT"
printf '%s\n' 'ps5-headless' > "$eden/GIT-REFSPEC"
# FFmpeg links configure probes through the compiler driver, not raw ld.
# Keep the derivative in our cache and regenerate its Makefile when it changes.
python3 - "$eden" "$scratch/build" <<'PY'
import pathlib, sys
source = pathlib.Path('.deps/mirror-5f142c7926d0c7fcbbd0ce30794d72f638a43b2a/externals/ffmpeg/CMakeLists.txt')
text = source.read_text()
for old, new in (
    ('--ld=${CMAKE_LINKER}', '--ld=${CMAKE_C_COMPILER}'),
    ('elseif (NOT (CMAKE_HOST_SYSTEM_PROCESSOR MATCHES CMAKE_SYSTEM_PROCESSOR\n    AND CMAKE_HOST_SYSTEM_NAME MATCHES CMAKE_SYSTEM_NAME))', 'elseif (CMAKE_CROSSCOMPILING)'),
    ('set(FFmpeg_MAKE_ARGS -j${SYSTEM_THREADS})', 'set(FFmpeg_MAKE_ARGS -j6)'),
):
    assert text.count(old) == 1, old
    text = text.replace(old, new)
target = pathlib.Path(sys.argv[1]) / 'externals/ffmpeg/CMakeLists.txt'
if target.read_text() != text:
    target.write_text(text)
    (pathlib.Path(sys.argv[2]) / '_deps/ffmpeg-build/Makefile').unlink(missing_ok=True)
PY
cmake -S "$eden" -B "$scratch/build" -G Ninja \
    ${darwin_zlib_include:+"$darwin_zlib_include"} \
    ${darwin_zlib_library:+"$darwin_zlib_library"} \
    ${darwin_icu_root:+"$darwin_icu_root"} \
    -DCMAKE_C_COMPILER=clang-18 -DCMAKE_CXX_COMPILER=clang++-18 \
    -DCMAKE_BUILD_TYPE=Release -DENABLE_LTO=OFF -DCMAKE_EXE_LINKER_FLAGS= -DEDEN_HOST_ASAN=OFF \
    -DEDEN_SHARED_JIT=OFF -DEDEN_JIT_COMPILE_BATCH=OFF \
    -DCMAKE_PROJECT_yuzu_INCLUDE="$root/headless/inject.cmake" \
    -DENABLE_QT=OFF -DYUZU_CMD=OFF -DYUZU_ROOM=OFF -DYUZU_ROOM_STANDALONE=OFF \
    -DYUZU_TESTS=OFF -DBUILD_TESTING=OFF -DENABLE_OPENGL=OFF -DENABLE_CUBEB=OFF \
    -DENABLE_WEB_SERVICE=OFF -DENABLE_LIBUSB=OFF -DYUZU_CRASH_DUMPS=OFF \
    -DYUZU_USE_EXTERNAL_FFMPEG=ON -DENABLE_WERROR=OFF -Dzstd_FORCE_BUNDLED=ON \
    -DDYNARMIC_ENABLE_NO_EXECUTE_SUPPORT=ON -DDYNARMIC_IGNORE_ASSERTS=OFF \
    -DSDL_UNIX_CONSOLE_BUILD=ON -DSDL_X11=OFF -DSDL_WAYLAND=OFF \
    -DSDL_OPENGL=OFF -DSDL_OPENGLES=OFF -DSDL_RENDER=OFF -DSDL_GPU=OFF
python3 -B "$root/headless/check_slab_lifetime.py" \
    "$scratch/build/headless/include/core/hle/kernel/slab_helpers.h" \
    "$scratch/source/src/core/hle/kernel/slab_helpers.h"
cmake --build "$scratch/build" --target eden-headless eden-romfs-check eden-devices-check eden-scalar-check eden-memory-check eden-ryujinx-check eden-shader-cache-check eden-mods-check eden-settings-check -j 6
python3 -B "$root/tools/check-sparse-header.py" "$scratch/build"
python3 -B "$root/tools/check-heap-growth.py"
python3 -B "$root/tools/check-crash-report.py"
"$scratch/build/bin/eden-scalar-check"
"$scratch/build/bin/eden-memory-check"
python3 -B "$root/headless/check_audio_shutdown.py" "$scratch/build/headless/core.cpp" "$scratch/source/src/core/core.cpp"
"$scratch/build/bin/eden-romfs-check"
"$scratch/build/bin/eden-ryujinx-check"
"$scratch/build/bin/eden-shader-cache-check"
"$scratch/build/bin/eden-mods-check"
"$scratch/build/bin/eden-settings-check"
bash tools/check-headless-devices.sh
cp "$scratch/build/bin/eden-headless" build/headless-host/eden-headless
cp "$scratch/build/compile_commands.json" build/headless-host/compile_commands.json
