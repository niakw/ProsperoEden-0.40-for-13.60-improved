#!/usr/bin/env python3
"""Exercise the PS5 host DNS shim against stubbed native resolver APIs.

This builds ONLY a tiny host C test harness. It does not compile Encore or
trigger a PS5 build, and makes no live network requests.
"""
from pathlib import Path
import os
import shutil
import sys
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
compat = root / "headless/ps5_net_compat.c"
src = r'''
#include <assert.h>
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <netdb.h>
#include <netinet/in.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
static int pool_created, pool_destroyed, resolver_created, resolver_destroyed, queried;
int sceNetPoolCreate(const char *name, int size, int flags) {
    assert(strcmp(name, "encore_dns") == 0 && size >= 16384 && flags == 0);
    ++pool_created; return 23;
}
int sceNetPoolDestroy(int pool) { assert(pool == 23); ++pool_destroyed; return 0; }
int sceNetResolverCreate(const char *name, int pool, int flags) {
    assert(strcmp(name, "encore_dns") == 0 && pool == 23 && flags == 0);
    ++resolver_created; return 24;
}
int sceNetResolverStartNtoa(int resolver, const char *host, struct in_addr *address,
                            int timeout, int retries, int flags) {
    assert(resolver == 24 && timeout > 0 && retries > 0 && flags == 0);
    ++queried;
    if (strcmp(host, "api.nlib.cc")) return -1;
    assert(inet_pton(AF_INET, "203.0.113.7", address) == 1);
    return 0;
}
int sceNetResolverDestroy(int resolver) {
    assert(resolver == 24); ++resolver_destroyed; return 0;
}
int __real_fcntl(int fd, int command, ...) {
    (void)fd;
    if (command == F_DUPFD) {
        va_list ap;
        va_start(ap, command);
        const int lowest = va_arg(ap, int);
        va_end(ap);
        assert(lowest == 3);
        return 117;
    }
    errno = EINVAL; return -1;
}
static int nonblocking = 0;
static int mock_setsockopt(int fd, int level, int opt, const void *value, socklen_t length) {
    assert(fd == 17 && level == SOL_SOCKET && opt == 0x1200);
    assert(length == sizeof(int));
    nonblocking = *(const int *)value;
    return 0;
}
static int mock_getsockopt(int fd, int level, int opt, void *value, socklen_t *length) {
    assert(fd == 17 && level == SOL_SOCKET && opt == 0x1200);
    assert(*length == sizeof(int));
    *(int *)value = nonblocking;
    return 0;
}
#define setsockopt mock_setsockopt
#define getsockopt mock_getsockopt
#include "ps5_net_compat.c"
#undef setsockopt
#undef getsockopt
int main(int argc, char** argv) {
    assert(argc == 2);
    assert(eden_network_filter_load(argv[1]) == 0);
    assert(eden_network_audit_init("network-audit-host-unwritten.log", 0) == 0);
    assert(eden_network_filter_count() >= 140);
    struct addrinfo hints = {0}, *addr = NULL;
    hints.ai_family = AF_INET;
    hints.ai_socktype = SOCK_STREAM;
    assert(getaddrinfo("api.nlib.cc", "443", &hints, &addr) == 0);
    assert(addr && addr->ai_family == AF_INET && addr->ai_socktype == SOCK_STREAM);
    const struct sockaddr_in *sa = (const struct sockaddr_in *)addr->ai_addr;
    assert(sa && ntohs(sa->sin_port) == 443);
    char ip[INET_ADDRSTRLEN] = {0}, port[12] = {0};
    assert(getnameinfo(addr->ai_addr, addr->ai_addrlen, ip, sizeof(ip),
                       port, sizeof(port), NI_NUMERICHOST | NI_NUMERICSERV) == 0);
    assert(strcmp(ip, "203.0.113.7") == 0 && strcmp(port, "443") == 0);
    char short_host[3] = {0}, short_service[2] = {0};
    assert(getnameinfo(addr->ai_addr, addr->ai_addrlen, short_host, sizeof(short_host),
                       NULL, 0, NI_NUMERICHOST) == EAI_OVERFLOW);
    assert(getnameinfo(addr->ai_addr, addr->ai_addrlen, NULL, 0,
                       short_service, sizeof(short_service), NI_NUMERICSERV) == EAI_OVERFLOW);
    freeaddrinfo(addr);
    assert(queried == 1 && pool_created == pool_destroyed);
    assert(resolver_created == resolver_destroyed);
    // Both exact suffix and nested-subdomain blocks reject BEFORE sceNetResolver.
    assert(getaddrinfo("api.ea.com", "443", &hints, &addr) == EAI_NONAME);
    assert(getaddrinfo("c.test.cdn.nintendo.net", "443", &hints, &addr) == EAI_NONAME);
    assert(getaddrinfo("not-ea.com", "443", &hints, &addr) == EAI_NONAME);
    assert(queried == 2); // not-ea.com is NOT blocked: resolver mock was queried
    assert(gethostbyname("login.api.ea.com") == NULL);
    assert(queried == 2);

    assert(getaddrinfo("127.0.0.1", "80", &hints, &addr) == 0);
    assert(queried == 2);
    freeaddrinfo(addr);
    assert(getaddrinfo("127.0.0.1", "not-a-port", &hints, &addr) == EAI_SERVICE);
    assert(getaddrinfo("127.0.0.1", "65536", &hints, &addr) == EAI_SERVICE);
    assert(getaddrinfo("127.0.0.1", "-1", &hints, &addr) == EAI_SERVICE);
    assert(getaddrinfo("127.0.0.1", "999999999999999999999999999999", &hints, &addr) == EAI_SERVICE);
    assert(getaddrinfo(NULL, NULL, &hints, &addr) == EAI_NONAME);
    assert(getaddrinfo("127.0.0.1", "https", &hints, &addr) == 0);
    assert(ntohs(((struct sockaddr_in *)addr->ai_addr)->sin_port) == 443);
    freeaddrinfo(addr);
    hints.ai_flags = AI_NUMERICSERV;
    assert(getaddrinfo("127.0.0.1", "https", &hints, &addr) == EAI_SERVICE);
    hints.ai_flags = 0;
    assert(getaddrinfo("unresolvable.invalid", "443", &hints, &addr) == EAI_NONAME);
    assert(addr == NULL);
    hints.ai_flags = AI_NUMERICHOST;
    assert(getaddrinfo("api.nlib.cc", "443", &hints, &addr) == EAI_NONAME);
    assert(queried == 3);
    hints.ai_family = AF_INET6;
    assert(getaddrinfo("::1", "443", &hints, &addr) == EAI_FAMILY);
    struct hostent *legacy = gethostbyname("api.nlib.cc");
    assert(legacy && legacy->h_addrtype == AF_INET && legacy->h_length == sizeof(struct in_addr));
    assert(legacy->h_addr_list && legacy->h_addr_list[0]);
    struct in_addr legacy_ip;
    memcpy(&legacy_ip, legacy->h_addr_list[0], sizeof(legacy_ip));
    char legacy_text[INET_ADDRSTRLEN] = {0};
    assert(inet_ntop(AF_INET, &legacy_ip, legacy_text, sizeof(legacy_text)));
    assert(strcmp(legacy_text, "203.0.113.7") == 0);
    assert(gethostbyname("unresolvable.invalid") == NULL);
    assert(queried == 5);
    assert(pool_created == pool_destroyed && resolver_created == resolver_destroyed);
    assert(__wrap_fcntl(17, F_DUPFD, 3) == 117);
    assert(__wrap_fcntl(17, F_SETFL, O_NONBLOCK) == 0);
    assert(nonblocking == 1);
    assert((__wrap_fcntl(17, F_GETFL) & O_NONBLOCK) != 0);
    assert(__wrap_fcntl(17, F_SETFL, O_RDWR) == 0);
    assert(nonblocking == 0);
    assert((__wrap_fcntl(17, F_GETFL) & O_NONBLOCK) == 0);
    puts("PS5 host DNS + SO_NBIO shim: mocked resolver, socket flags and cleanup PASS");
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix="encore-ps5-net-unit-") as tmp:
    tmp = Path(tmp)
    source = tmp / "ps5_net_unit.c"
    binary = tmp / "ps5_net_unit"
    source.write_text(src)
    sdk = os.environ.get("SDKROOT", "/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk")
    env = dict(os.environ, SDKROOT=sdk)
    # Apple Clang supplies the macOS-matched sanitizer runtime. Homebrew LLVM 18
    # comes first on PATH after eden_host_env() and its ASan binary can hang at
    # startup on this machine, so do not select it for this *host* unit test.
    cc = "/usr/bin/clang" if sys.platform == "darwin" else (shutil.which("clang-18") or shutil.which("clang"))
    assert cc is not None, "Clang is required for host sanitizer micro-test"
    subprocess.run([cc, "-std=c11", "-D_DEFAULT_SOURCE", "-Wall", "-Wextra", "-Werror",
                    "-fsanitize=address,undefined", "-I", str(compat.parent),
                    "-pthread", str(source), str(root / "headless/network_domain_rules.c"),
                    str(root / "headless/network_audit.c"),
                    "-o", str(binary)], check=True, env=env)
    subprocess.run([str(binary), str(root / "headless/network-hosts.txt")],
                   check=True, env=env, timeout=8)
