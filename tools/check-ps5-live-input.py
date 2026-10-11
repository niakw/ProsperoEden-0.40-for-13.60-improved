#!/usr/bin/env python3
"""Regression for PS5 live DualSense default in FC27 all-on builds.

The previous development build autobooted FC27 *and* silently replaced live
controller polling with timed fake presses, making the quit chord impossible.
Compile and run the actual pure C++ replay policy; inspect its PS5 glue.
This does not prove a PS5 hardware input sample or in-game glyph artwork.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
src = (ROOT / "headless/main.cpp").read_text()
pad = (ROOT / "headless/pad.cpp").read_text()
header = (ROOT / "headless/dev_replay_policy.h").read_text()

assert '#include "dev_replay_policy.h"' in src
assert 'bool replay_requested = false;' in src
assert 'Eden::DevInput::ReplayRequestedAfter(replay_requested, entry)' in src
assert 'Eden::DevInput::ScriptedReplayEnabled(' in src
assert 'replay_requested, development_id, EDEN_DEV_PROFILE_TITLE)' in src
assert 'if (!timed_replay) {' in src and 'pad->Poll();' in src
assert 'compat_input_requested' in src
assert 'EDEN_PAD_INPUT mode=%s replay_requested=%d' in src
assert 'development_id == EDEN_DEV_PROFILE_TITLE && !replay_off' not in src
assert 'constexpr ButtonMask menu_chord = kButtonTouchPad | kButtonL1;' in pad
assert 'return_to_menu = true;' in pad
assert 'if (pad->TakeReturnToMenu()) {' in src
assert 'completion->return_to_menu = true;' in src
assert 'if (!completion->guest_fault.empty() && !return_to_menu) {' in src
assert 'if (return_to_menu) continue;' in src
assert 'if (token == "replay=on") return true;' in header
assert 'if (token == "replay=off") return false;' in header

cxx = next((name for name in ("clang++-18", "clang++", "g++") if shutil.which(name)), None)
if not cxx:
    raise SystemExit("C++20 compiler required for PS5 replay policy mock")
fixture = r"""
#include "dev_replay_policy.h"
#include <cassert>
using Eden::DevInput::ReplayRequestedAfter;
using Eden::DevInput::ScriptedReplayEnabled;
int main() {
    constexpr auto title = "0100C49025D3E000";
    static_assert(!ScriptedReplayEnabled(false, title, title));
    static_assert(!ScriptedReplayEnabled(false, "ZELDA", title));
    static_assert( ScriptedReplayEnabled(true, title, title));
    static_assert(!ScriptedReplayEnabled(true, "ZELDA", title));
    static_assert(!ReplayRequestedAfter(false, "launcher=first"));
    static_assert( ReplayRequestedAfter(false, "replay=on"));
    static_assert(!ReplayRequestedAfter(true, "replay=off"));
    static_assert( ReplayRequestedAfter(true, "rom=0100C49025D3E000"));
    bool requested = false; // No dev-settings file: interactive by default.
    assert(!ScriptedReplayEnabled(requested, title, title));
    for (auto setting : {"cache_spin=200", "jit_shared=off", "rom=0100C49025D3E000"})
        requested = ReplayRequestedAfter(requested, setting);
    assert(!ScriptedReplayEnabled(requested, title, title));
    requested = ReplayRequestedAfter(requested, "replay=on");
    assert(ScriptedReplayEnabled(requested, title, title));
    requested = ReplayRequestedAfter(requested, "replay=off");
    assert(!ScriptedReplayEnabled(requested, title, title));
}
"""
with tempfile.TemporaryDirectory(prefix="eden-live-dualsense-") as tmp:
    source = Path(tmp) / "live_input.cpp"
    app = Path(tmp) / "live_input"
    source.write_text(fixture)
    subprocess.run([cxx, "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
                    "-I", str(ROOT / "headless"), str(source), "-o", str(app)], check=True)
    subprocess.run([str(app)], check=True)
print("PASS: FC27 all-on uses real DualSense unless replay=on is explicitly requested")
print("Shortcut detection remains touchpad + L1; physical input and glyph art require PS5 validation")
