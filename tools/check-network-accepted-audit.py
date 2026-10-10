#!/usr/bin/env python3
"""Compile actual opt-in audit C logger; assert bounded, quiet and DNS-neutral.

Only host POSIX fixtures run here. Real PS5 SDK/native runtime still require CI.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
main=(root/"headless/main.cpp").read_text()
services=(root/"headless/prosperoeden/eden_services.cpp").read_text()
cmake=(root/"headless/CMakeLists.txt").read_text()
native=(root/"headless/ps5_net_compat.c").read_text()
observer=(root/"headless/network_audit_sockets.c").read_text()
for must in (
    'eden_network_audit_init(Eden::LogFile("network-accepted.log").c_str()',
    'persist_detailed_logs ? 1 : 0',
):
    assert must in main
assert 'eden_network_audit_enable(value.detailed_logging ? 1 : 0);' in services
for label in ('network_audit.c','network_audit_sockets.c'):
    assert '${EDEN_PORT_DIR}/'+label in cmake
for function in ('connect','send','sendto','recv','recvfrom'):
    assert '-Wl,--wrap='+function in cmake
    assert '__wrap_'+function in observer and '__real_'+function in observer
for kind in ('dns-denied','dns-resolved','dns-error'):
    assert '"'+kind+'"' in native
# No DNS/global console configuration is changed by these new functions.
for forbidden in ('resolv.conf','sceNetResolverStartNtoa(', 'sceNetInit(', 'setdns',
                  'sceNetCtlSetInfo', 'setenv(', 'system('):
    assert forbidden not in (root/"headless/network_audit.c").read_text()
    assert forbidden not in observer
# The expensive formatting is guarded in every call site when OFF.
assert 'if (!atomic_load_explicit(&audit_enabled,memory_order_acquire)) return;' in (
    root/"headless/network_audit.c").read_text()
assert 'if (eden_network_audit_active()' in observer or 'eden_network_audit_active())' in observer
# The generated guest service inherits the existing DNS denylist, not a new resolver.
assert 'eden_network_host_blocked(host.c_str())' in cmake
assert '"guest", "tx"' not in cmake or 'eden_network_audit_event' in cmake
assert 'file(READ "${PROJECT_SOURCE_DIR}/src/core/hle/service/sockets/bsd.cpp" audited_bsd)' in cmake
for source in ("audited_guest_dns.cpp","audited_guest_bsd.cpp"):
    assert 'list(APPEND core_sources "${PORT_BUILD_DIR}/'+source+'")' in cmake
for key in ("new_dns_gate","bsd_audit_connect","bsd_send_audit","bsd_sendto_audit"):
    assert "string(CONCAT "+key in cmake, "CMake set() would introduce semicolons into C++"

c=r"""
#include "network_audit.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static int exists(const char* path) {
    FILE* f=fopen(path,"rb");
    if (!f) return 0;
    fclose(f); return 1;
}
static long bytes(const char* path) {
    FILE* f=fopen(path,"rb");
    assert(f);
    assert(fseek(f,0,SEEK_END)==0);
    long n=ftell(f); fclose(f); return n;
}
static int contains(const char* path,const char* phrase) {
    FILE* f=fopen(path,"rb"); assert(f);
    char row[640]; int found=0;
    while (fgets(row,sizeof(row),f)) if (strstr(row,phrase)) found=1;
    fclose(f); return found;
}
int main(int argc,char** argv) {
    assert(argc==2);
    char logpath[640],oldpath[650];
    snprintf(logpath,sizeof(logpath),"%s/network-accepted.log",argv[1]);
    snprintf(oldpath,sizeof(oldpath),"%s.prev",logpath);
    assert(!eden_network_audit_active());
    assert(eden_network_audit_init(logpath,0)==0);
    eden_network_audit_event("launcher","dns-resolved","api.nlib.cc",0,0);
    eden_network_audit_event("guest","tx","fd:9",123,0);
    assert(!exists(logpath));
    eden_network_audit_enable(1);
    assert(eden_network_audit_active());
    eden_network_audit_event("launcher","dns-resolved","api.nlib.cc",0,0);
    eden_network_audit_event("guest","dns-denied","api.ea.com",0,1);
    eden_network_audit_event("guest","tx","198.51.100.1:443",135,0);
    eden_network_audit_event("guest","tx","evil\nline",10,0);
    eden_network_audit_enable(0);
    assert(!eden_network_audit_active());
    assert(exists(logpath));
    assert(contains(logpath,"scope=launcher event=dns-resolved target=api.nlib.cc"));
    assert(contains(logpath,"scope=guest event=dns-denied target=api.ea.com"));
    assert(contains(logpath,"scope=guest event=tx target=198.51.100.1:443 bytes=135"));
    assert(contains(logpath,"target=evil_line"));
    const long initial=bytes(logpath);
    eden_network_audit_event("guest","tx","no-quiet-write",500,0);
    assert(bytes(logpath)==initial);
    eden_network_audit_enable(1);
    for (int i=0;i<80000;i++)
        eden_network_audit_event("guest","tx","203.0.113.10:12345",1000,0);
    eden_network_audit_enable(0);
    assert(exists(logpath)&&exists(oldpath));
    assert(bytes(logpath)<=4*1024*1024);
    assert(bytes(oldpath)<=4*1024*1024+512);
    puts("NETWORK_AUDIT_HOST_PASS: quiet, live toggle, escaping, 4MiB rotation");
    return 0;
}
"""
compiler=shutil.which("clang-18") or shutil.which("clang") or shutil.which("cc")
assert compiler
with tempfile.TemporaryDirectory(prefix="eden-audit-host-") as path:
    path=Path(path)
    program=path/"main.c"
    program.write_text(c)
    exe=path/"audit"
    subprocess.run([compiler,"-std=c11","-D_DEFAULT_SOURCE","-O1","-pthread",
                    "-Wall","-Wextra","-Werror","-fsanitize=address,undefined",
                    "-I"+str(root/"headless"),
                    str(root/"headless/network_audit.c"),str(program),
                    "-o",str(exe)],check=True)
    subprocess.run([str(exe),str(path)],check=True,timeout=20)
print("Source guard: native+guest audit hooks do not alter DNS settings or network delivery")
