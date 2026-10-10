/*
 * Encore native PS5 host-network socket compatibility.
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Native-title resolver imports can point at libScePosixForWebKit, which Encore
 * does not load, so host DNS is implemented directly on sceNetResolver.
 * Native PS5 libc can also reject fcntl operations on sockets with EINVAL.
 * cpp-httplib needs F_GETFL/F_SETFL for non-blocking connects, so only that
 * refused socket path is translated to the console's SO_NBIO option.
 * Successful/non-socket fcntl calls are forwarded intact.
 */
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <netdb.h>
#include <netinet/in.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include "network_domain_rules.h"
#include "network_audit.h"

enum { EDEN_PS5_SO_NBIO = 0x1200 };

extern int sceNetPoolCreate(const char *name, int size, int flags);
extern int sceNetPoolDestroy(int pool);
extern int sceNetResolverCreate(const char *name, int pool, int flags);
extern int sceNetResolverStartNtoa(int resolver, const char *hostname, struct in_addr *address,
                                   int timeout_us, int retries, int flags);
extern int sceNetResolverDestroy(int resolver);
extern int __real_fcntl(int descriptor, int command, ...);

/*
 * Native-title SDK getaddrinfo imports can resolve through libScePosixForWebKit,
 * which is not loaded by Encore. Resolve IPv4 names explicitly through sceNetResolver.
 * This is the same hardware-proven strategy used by ps5-native-app-boilerplate.
 */
static int eden_ps5_lookup(const char *name, struct in_addr *address)
{
    if (inet_pton(AF_INET, name, address) == 1) {
        eden_network_audit_event("launcher", "numeric-ip", name, 0, 0);
        return 0;
    }
    const int pool = sceNetPoolCreate("encore_dns", 16 * 1024, 0);
    if (pool < 0)
        return EAI_MEMORY;
    int result = EAI_FAIL;
    const int resolver = sceNetResolverCreate("encore_dns", pool, 0);
    if (resolver >= 0)
    {
        result = sceNetResolverStartNtoa(resolver, name, address, 5000000, 2, 0) < 0 ?
                     EAI_NONAME : 0;
        (void)sceNetResolverDestroy(resolver);
    }
    (void)sceNetPoolDestroy(pool);
    eden_network_audit_event("launcher",
                             result == 0 ? "dns-resolved" : "dns-error",
                             name, 0, result);
    return result;
}

int getaddrinfo(const char *node, const char *service, const struct addrinfo *hints,
                struct addrinfo **result)
{
    if (result == NULL)
        return EAI_FAIL;
    *result = NULL;
    if (node == NULL && service == NULL)
        return EAI_NONAME;
    const int family = hints != NULL ? hints->ai_family : AF_UNSPEC;
    if (family != AF_UNSPEC && family != AF_INET)
        return EAI_FAMILY;
    if (node != NULL && eden_network_host_blocked(node)) {
        eden_network_audit_event("launcher", "dns-denied", node, 0, EAI_NONAME);
        return EAI_NONAME;
    } // launcher and games share the exact same denylist

    struct in_addr address;
    address.s_addr = htonl(INADDR_LOOPBACK);
    if (node != NULL)
    {
        if (hints != NULL && (hints->ai_flags & AI_NUMERICHOST) != 0)
        {
            if (inet_pton(AF_INET, node, &address) != 1)
                return EAI_NONAME;
        }
        else
        {
            const int failed = eden_ps5_lookup(node, &address);
            if (failed != 0)
                return failed;
        }
    }
    else if (hints != NULL && (hints->ai_flags & AI_PASSIVE) != 0)
    {
        address.s_addr = htonl(INADDR_ANY);
    }

    // A malformed or out-of-range service must not silently become port zero.
    // The HTTP client normally passes a numeric port, but traditional service
    // names remain useful for other host-network callers.
    unsigned port = 0;
    if (service != NULL)
    {
        if (strcmp(service, "http") == 0 &&
            (hints == NULL || (hints->ai_flags & AI_NUMERICSERV) == 0))
            port = 80;
        else if (strcmp(service, "https") == 0 &&
                 (hints == NULL || (hints->ai_flags & AI_NUMERICSERV) == 0))
            port = 443;
        else
        {
            const unsigned char *digit = (const unsigned char *)service;
            if (*digit == 0)
                return EAI_SERVICE;
            for (; *digit != 0; ++digit)
            {
                if (*digit < '0' || *digit > '9')
                    return EAI_SERVICE;
                const unsigned next_digit = (unsigned)(*digit - '0');
                if (port > (65535u - next_digit) / 10u)
                    return EAI_SERVICE;
                port = port * 10u + next_digit;
            }
        }
    }

    struct addrinfo *entry = calloc(1, sizeof(struct addrinfo) + sizeof(struct sockaddr_in));
    if (entry == NULL)
        return EAI_MEMORY;
    struct sockaddr_in *in = (struct sockaddr_in *)(entry + 1);
#if defined(PS5_NATIVE) || defined(__APPLE__) || defined(__FreeBSD__)
    in->sin_len = sizeof(*in);
#endif
    in->sin_family = AF_INET;
    in->sin_port = htons((uint16_t)port);
    in->sin_addr = address;
    entry->ai_family = AF_INET;
    entry->ai_socktype = hints != NULL && hints->ai_socktype != 0 ? hints->ai_socktype : SOCK_STREAM;
    entry->ai_protocol = hints != NULL ? hints->ai_protocol : 0;
    entry->ai_addrlen = sizeof(*in);
    entry->ai_addr = (struct sockaddr *)in;
    *result = entry;
    return 0;
}

void freeaddrinfo(struct addrinfo *entry)
{
    while (entry != NULL)
    {
        struct addrinfo *next = entry->ai_next;
        free(entry);
        entry = next;
    }
}

const char *gai_strerror(int code)
{
    switch (code)
    {
    case 0: return "no error";
    case EAI_NONAME: return "the name was not found";
    case EAI_FAMILY: return "address family not supported";
    case EAI_MEMORY: return "out of memory";
    default: return "the name lookup failed";
    }
}

struct hostent *gethostbyname(const char *name)
{
    // Legacy users of the host resolver must not silently receive a NULL stub.
    // gethostbyname's storage is caller-thread-local, as with traditional libc.
    static _Thread_local struct hostent host;
    static _Thread_local struct in_addr address;
    static _Thread_local char hostname[256];
    static _Thread_local char *aliases[1];
    static _Thread_local char *addresses[2];
    if (eden_network_host_blocked(name)) {
        eden_network_audit_event("launcher", "dns-denied", name, 0, EAI_NONAME);
        return NULL;
    }
    if (name == NULL || strlen(name) >= sizeof(hostname) ||
        eden_ps5_lookup(name, &address) != 0)
        return NULL;
    memcpy(hostname, name, strlen(name) + 1);
    aliases[0] = NULL;
    addresses[0] = (char *)&address;
    addresses[1] = NULL;
    host.h_name = hostname;
    host.h_aliases = aliases;
    host.h_addrtype = AF_INET;
    host.h_length = sizeof(address);
    host.h_addr_list = addresses;
    return &host;
}

// Match PS5 Payload SDK (size_t buffer lengths) and Darwin (socklen_t).
int getnameinfo(const struct sockaddr *address, socklen_t length, char *host,
#if defined(PS5_NATIVE) || defined(__FreeBSD__)
                size_t host_size, char *service, size_t service_size, int flags)
#else
                socklen_t host_size, char *service, socklen_t service_size, int flags)
#endif
{
    (void)flags;
    if (address == NULL || address->sa_family != AF_INET || length < sizeof(struct sockaddr_in))
        return EAI_FAMILY;
    const struct sockaddr_in *in = (const struct sockaddr_in *)address;
    if (host != NULL)
    {
        char numeric[INET_ADDRSTRLEN];
        if (inet_ntop(AF_INET, &in->sin_addr, numeric, sizeof(numeric)) == NULL)
            return EAI_FAIL;
        const size_t needed = strlen(numeric) + 1;
        if (host_size < needed)
            return EAI_OVERFLOW;
        memcpy(host, numeric, needed);
    }
    if (service != NULL)
    {
        char numeric[6]; // decimal representation of any 16-bit port + NUL
        const int needed = snprintf(numeric, sizeof(numeric), "%u", (unsigned)ntohs(in->sin_port));
        if (needed < 0 || service_size <= (size_t)needed)
            return EAI_OVERFLOW;
        memcpy(service, numeric, (size_t)needed + 1);
    }
    return 0;
}

static int eden_ps5_socket_flags(int socket, int command, intptr_t value)
{
    switch (command)
    {
    case F_GETFD:
    case F_SETFD:
        return 0; /* a native title never execs another process */
    case F_SETFL:
    {
        const int on = (((int)value) & O_NONBLOCK) != 0;
        return setsockopt(socket, SOL_SOCKET, EDEN_PS5_SO_NBIO, &on, sizeof(on));
    }
    case F_GETFL:
    {
        int on = 0;
        socklen_t length = sizeof(on);
        if (getsockopt(socket, SOL_SOCKET, EDEN_PS5_SO_NBIO, &on, &length) < 0)
            return -1;
        return O_RDWR | (on ? O_NONBLOCK : 0);
    }
    default:
        errno = EINVAL;
        return -1;
    }
}

int __wrap_fcntl(int descriptor, int command, ...)
{
    intptr_t argument = 0;
    int result = -1;

    if (command == F_GETFD || command == F_GETFL)
    {
        result = __real_fcntl(descriptor, command);
    }
    else
    {
        va_list arguments;
        va_start(arguments, command);
        // F_DUPFD (used by log_pipe.h), F_SETFL and F_SETFD all take a
        // promoted int. Reading one as intptr_t via va_arg is undefined behavior.
        const int takes_int = command == F_DUPFD || command == F_SETFL || command == F_SETFD;
        argument = takes_int ? (intptr_t)va_arg(arguments, int)
                             : va_arg(arguments, intptr_t);
        va_end(arguments);
        // The forwarded variadic call must use the original promoted argument type too.
        result = takes_int ? __real_fcntl(descriptor, command, (int)argument)
                           : __real_fcntl(descriptor, command, argument);
    }

    if (result >= 0 || errno != EINVAL)
        return result;
    if (command == F_GETFD || command == F_SETFD || command == F_SETFL || command == F_GETFL)
        return eden_ps5_socket_flags(descriptor, command, argument);
    return result;
}
