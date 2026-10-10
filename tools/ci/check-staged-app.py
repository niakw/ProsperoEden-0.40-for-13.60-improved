#!/usr/bin/env python3
"""Validate a staged PPSA99008 artifact without requiring compile-directory metadata."""
from pathlib import Path
import json
import os
import sys

root = Path(__file__).resolve().parents[2]
app = Path(sys.argv[1] if len(sys.argv) > 1 else root / "build/release/PPSA99008").resolve()
assert app.name == "PPSA99008" and app.is_dir(), app

base = {
    "eboot.bin", "core-homebrew.nro", "sandbox-elevator.elf", "network-hosts.txt",
    "sce_module/libc.prx", "sce_sys/param.json", "sce_sys/icon0.png", "sce_sys/icon0.dds",
    "sce_sys/pic0.dds", "sce_sys/pic1.dds", "sce_sys/snd0.at9",
}
source_ui = root / "headless/prosperoeden/ui"
ui_expected = {
    "ui/" + p.relative_to(source_ui).as_posix()
    for p in source_ui.rglob("*") if p.is_file()
}
ui_expected.discard("ui/art/backdrop-blur.tga")
ui_expected.add("ui/art/backdrop.tga")
for source in (source_ui / "lang").glob("*.po"):
    ui_expected.add("ui/lang/" + source.with_suffix(".txt").name)
legal_source = root / "LICENSES"
legal_expected = {"legal/LICENSE", "legal/THIRD_PARTY_NOTICES.md"} | {
    "legal/LICENSES/" + p.name for p in legal_source.iterdir() if p.is_file()
}
expected = base | ui_expected | legal_expected
actual = {p.relative_to(app).as_posix() for p in app.rglob("*") if p.is_file()}
missing = sorted(expected - actual)
extra = sorted(actual - expected)
assert not missing and not extra, f"package inventory mismatch missing={missing} extra={extra}"
assert (app / "network-hosts.txt").read_bytes() == (root / "headless/network-hosts.txt").read_bytes(), "stale/missing packaged network denylist"
for name in expected:
    p = app / name
    assert not p.is_symlink(), name
    assert p.stat().st_size > 0, name

param = json.loads((app / "sce_sys/param.json").read_text())
assert param["titleId"] == "PPSA99008"
assert param["contentId"].endswith("PROSPEROEDEN0001")
assert param["localizedParameters"]["en-US"]["titleName"] == "Prospero.Eden Encore"
assert (app / "sce_sys/icon0.png").read_bytes() == (root / "assets/icon0.png").read_bytes()
assert (app / "sce_sys/icon0.dds").read_bytes() == (root / "assets/icon0.dds").read_bytes()
source_lang = sorted((source_ui / "lang").glob("*.po"))
staged_lang = sorted((app / "ui/lang").glob("*.po"))
assert len(source_lang) == 29, f"expected 29 launcher catalogs, got {len(source_lang)}"
assert [p.name for p in staged_lang] == [p.name for p in source_lang], "launcher catalog inventory differs"
assert any(p.name == "fr-FR.po" for p in staged_lang), "fr-FR launcher catalog missing"
for source in source_lang:
    staged = app / "ui/lang" / source.name
    companion = app / "ui/lang" / source.with_suffix(".txt").name
    assert staged.read_bytes() == source.read_bytes(), f"stale/corrupt launcher catalog: {source.name}"
    assert companion.read_bytes() == source.read_bytes(), f"stale/corrupt launcher catalog companion: {companion.name}"
assert (app / "sandbox-elevator.elf").stat().st_size > 0
eboot = (app / "eboot.bin").read_bytes()
assert len(eboot) > 1024 * 1024
# The earlier "Nlib hero cached for " diagnostic was intentionally removed when
# banner/icon/screens requests became concurrent for every installed game.
# Keep the authoritative, still-compiled EDEN_NLIB_RESULT and live Nlib API
# endpoint markers. Do NOT insist on historical debug strings in shipping code.
# The native build cache once shipped a stale launcher while packaging current art/catalogs.
# These literals prove the redesigned Home, in-binary French fallback, Nlib enrichment and PS5 HID
# watchdog were all compiled into the shipping binary rather than merely present in the checkout.
for text in (
    "QUICK SETTINGS", "SELECTED GAME", "Confirm this action?", "PARAMÈTRES RAPIDES",
    "api.nlib.cc", "EDEN_NLIB_RESULT title_id=",
    "/banner/1080p", "/screen/", "fields=name,intro,description,publisher,developer,releaseDate",
    "BUTTON PROFILE", "PlayStation", "Custom PS5", "Custom Switch",
    "EDEN_PAD_MAPPING_FIXED title=", "EDEN_PAD_MAPPING_LOCKED scope=session mode=static",
    "Minimum", "Recommended", "High", "Ultra",
    "EDEN_HID_NPAD update={}", "EDEN_JIT_ALIAS rx=",
):
    marker = text.encode("utf-8")
    assert marker in eboot, f"stale launcher binary: missing {marker!r}"

nlib_source = (root / "headless/prosperoeden/eden_services.cpp").read_text()
assert 'const int wanted_screens = std::clamp(screen_count, 0, 3);' in nlib_source, "all advertised Nlib screens must be fetched"
assert 'std::vector<std::future<bool>> downloads;' in nlib_source, "complete media downloads must be concurrent"
home_source = (root / "headless/prosperoeden/pe/ui/home.cpp").read_text()
library_source = (root / "headless/prosperoeden/pe/ui/library.cpp").read_text()
assert "Confirmation::launch_game" not in home_source + library_source, "launch still asks for confirmation"
assert "open_game_settings_at_file" in home_source, "Home Triangle no longer opens per-game settings"
assert "recent.hero" in home_source, "recent-game Nlib artwork is not used by Home"
assert "hero_intro" in home_source, "Nlib intro is not used by Home hero"
assert "game->screenshots" in library_source, "Nlib screenshots are not used by Library"
assert "VIEW ALL GAMES" not in home_source, "removed Home pseudo-link returned"
assert all(marker in home_source for marker in (
    "kHomeQuickPanel", "kHomeQuickFirst", "kHomeStorage", "kHomeControllers", "kHomeFullSettings",
)), "final Home navigation/utility contract missing"
assert "const Rect hero{0.0f, 0.0f, 1920.0f, 1080.0f}" in home_source, "reference hero is not full bleed"
assert "const Cover hero_picture = c.textures.cover(hero_artwork, 1920.0f)" in home_source, "Nlib hero is not full bleed"
assert "utility_card(3" in home_source, "reference four utilities missing"
assert "Cross launches" not in library_source, "text-only controller hint returned"
print(f"Staged Encore artifact PASS ({len(actual)} files, current launcher/runtime markers present)")
