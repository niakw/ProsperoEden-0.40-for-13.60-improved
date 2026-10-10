#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compile & execute the actual shared hosts matcher for launcher and guest.

Domain suffixes include the apex and arbitrary subdomains; '*' is label-safe.
All unexpected/missing/corrupted packaged policies fail closed.
"""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
hosts = root / "headless/network-hosts.txt"
rules = [line.strip() for line in hosts.read_text().splitlines()
         if line.strip() and not line.lstrip().startswith("#")]
assert len(rules) >= 140
assert len(rules) == len(set(rules))
for domain in ("nintendo.com","nintendo.net","nintendoswitch.com.cn",
               "nintendods.cz","ea.com","epicgames.com","ubi-services.com",
               "xboxlive.com","pokemon.com","gogcdn.net",
               "scsi-upload-lp1.s3.us-west-2.amazonaws.com"):
    assert domain in rules
# Redundancy check: a nested domain already covered by a base rule is omitted.
for redundant in ("api.ea.com","accounts.nintendo.com",
                  "ctest.cdn.nintendo.net","shift.gearboxsoftware.com",
                  "api.epicgames.dev","gw.hac.lp1.vermillion.srv.nintendo.net"):
    assert redundant not in rules
assert "nlib.cc" not in rules and "github.com" not in rules
code = r"""
#include "network_domain_rules.h"
#include <assert.h>
#include <stdio.h>
static void yes(const char* name) { assert(eden_network_host_blocked(name) == 1); }
static void no(const char* name) { assert(eden_network_host_blocked(name) == 0); }
int main(int argc, char** argv) {
    assert(argc==3);
    // Before loading any rules, do not accidentally enable unfiltered DNS.
    yes("api.nlib.cc");
    assert(eden_network_filter_load("/no/such/network-hosts.txt") != 0);
    yes("not-yet-initialized.example");
    assert(eden_network_filter_load(argv[1]) == 0);
    assert(eden_network_filter_count() >= 140);
    yes("ea.com");
    yes("API.ea.com");
    yes("login.a.b.EA.COM.");
    yes("accounts.nintendo.com");
    yes("ctest-ul-lp1.cdn.nintendo.net");
    yes("scsi-upload-lp1.s3.us-west-2.amazonaws.com");
    yes("epicgames.dev");
    yes("api.epicgames.dev");
    yes("hub.gogcdn.net");
    yes("www.pokemon.co.jp");
    yes("forge.nintendods.cz");
    no("not-ea.com");
    // These names were blocked by the old hardcoded Eden table but are
    // absent from the supplied policy; allow them through to normal DNS.
    no("microsoft.com");
    no("phoenix-api.wbagora.com");
    no("battlenet.com.evil.test");
    no("ea.com.evil.example");
    no("fake-nintendo.com");
    no("nintendowifi.net.evil.org");
    no("other.s3.us-west-2.amazonaws.com");
    no("api.nlib.cc");
    no("raw.githubusercontent.com");
    no("example.org");
    no("8.8.8.8"); // raw IP bypass is documented, not a domain security guarantee
    yes("broken..domain");
    yes(NULL);
    // Exact '*' patterns from the user's examples are tested separately.
    assert(eden_network_filter_load(argv[2]) != 0); // cannot mutate active policy
    puts("PASS: 145+ host rules, subdomains, canonical names, suffix boundaries and fail closed");
    return 0;
}
"""
wildcard = r"""
#include "network_domain_rules.h"
#include <assert.h>
int main(int argc, char** argv) {
    assert(argc==2);
    assert(eden_network_filter_load(argv[1])==0);
    assert(eden_network_host_blocked("alpha.test.fr"));
    assert(eden_network_host_blocked("api.alpha.test.fr"));
    assert(eden_network_host_blocked("api.test.org"));
    assert(eden_network_host_blocked("alpha.betatEst.fr"));
    assert(!eden_network_host_blocked("test.org"));
    assert(!eden_network_host_blocked("api.untested.org"));
    assert(!eden_network_host_blocked("hello.example"));
}
"""
c = shutil.which("clang") or shutil.which("cc")
assert c, "C compiler is required"
with tempfile.TemporaryDirectory(prefix="encore-network-hosts-") as dir:
    tmp=Path(dir)
    rules_fixture = tmp/"wildcard-hosts.txt"
    rules_fixture.write_text("*.test.*\n*.*test.fr\n")
    for which,source,arg in [
        ("main",code,[str(hosts),str(rules_fixture)]),
        ("wildcard",wildcard,[str(rules_fixture)]),
    ]:
        file=tmp/(which+".c")
        file.write_text(source)
        exe=tmp/which
        subprocess.run([c,"-std=c11","-O2","-Wall","-Wextra","-Werror",
                        "-I"+str(root/"headless"),
                        str(root/"headless/network_domain_rules.c"),
                        str(file),"-o",str(exe)],check=True)
        subprocess.run([str(exe),*arg],check=True,timeout=10)
print("Host network policy: compiled and passed (PS5 SDK & guest socket integration untested)")
