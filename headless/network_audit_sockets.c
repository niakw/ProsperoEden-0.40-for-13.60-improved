// SPDX-License-Identifier: GPL-3.0-or-later
// PS5 process-local POSIX BSD socket observation only. Never changes DNS,
// SceNet configuration, arguments, return values or observed errno.
#include "network_audit.h"
#include <arpa/inet.h>
#include <errno.h>
#include <netinet/in.h>
#include <stdio.h>
#include <sys/socket.h>
#include <sys/types.h>

extern int __real_connect(int, const struct sockaddr*, socklen_t);
extern ssize_t __real_send(int, const void*, size_t, int);
extern ssize_t __real_sendto(int, const void*, size_t, int,
                            const struct sockaddr*, socklen_t);
extern ssize_t __real_recv(int, void*, size_t, int);
extern ssize_t __real_recvfrom(int, void*, size_t, int,
                              struct sockaddr*, socklen_t*);

static void socket_target(int fd, const struct sockaddr* addr, socklen_t length,
                          char* output, size_t cap) {
    const struct sockaddr* peer=addr;
    struct sockaddr_storage storage;
    socklen_t plen=sizeof(storage);
    if (!peer && getpeername(fd,(struct sockaddr*)&storage,&plen)==0) {
        peer=(const struct sockaddr*)&storage;
        length=plen;
    }
    if (peer && peer->sa_family==AF_INET && length>=sizeof(struct sockaddr_in)) {
        const struct sockaddr_in* in=(const struct sockaddr_in*)peer;
        char ip[INET_ADDRSTRLEN];
        if (inet_ntop(AF_INET,&in->sin_addr,ip,sizeof(ip))) {
            (void)snprintf(output,cap,"%s:%u",ip,(unsigned)ntohs(in->sin_port));
            return;
        }
    }
    (void)snprintf(output,cap,"fd:%d",fd);
}
int __wrap_connect(int fd, const struct sockaddr* addr, socklen_t length) {
    const int ret=__real_connect(fd,addr,length);
    const int saved=errno;
    if (eden_network_audit_active() && (ret==0 || saved==EINPROGRESS)) {
        char target[80]; socket_target(fd,addr,length,target,sizeof(target));
        eden_network_audit_event("launcher","connect",target,0,ret==0?0:EINPROGRESS);
    }
    errno=saved;
    return ret;
}
ssize_t __wrap_send(int fd, const void* buffer, size_t length, int flags) {
    const ssize_t ret=__real_send(fd,buffer,length,flags);
    const int saved=errno;
    if (ret>0 && eden_network_audit_active()) {
        char target[80]; socket_target(fd,NULL,0,target,sizeof(target));
        eden_network_audit_event("launcher","tx",target,(unsigned long long)ret,0);
    }
    errno=saved;
    return ret;
}
ssize_t __wrap_sendto(int fd, const void* buffer, size_t length, int flags,
                      const struct sockaddr* addr, socklen_t addr_len) {
    const ssize_t ret=__real_sendto(fd,buffer,length,flags,addr,addr_len);
    const int saved=errno;
    if (ret>0 && eden_network_audit_active()) {
        char target[80]; socket_target(fd,addr,addr_len,target,sizeof(target));
        eden_network_audit_event("launcher","tx",target,(unsigned long long)ret,0);
    }
    errno=saved;
    return ret;
}
ssize_t __wrap_recv(int fd, void* buffer, size_t length, int flags) {
    const ssize_t ret=__real_recv(fd,buffer,length,flags);
    const int saved=errno;
    if (ret>0 && eden_network_audit_active()) {
        char target[80]; socket_target(fd,NULL,0,target,sizeof(target));
        eden_network_audit_event("launcher","rx",target,(unsigned long long)ret,0);
    }
    errno=saved;
    return ret;
}
ssize_t __wrap_recvfrom(int fd, void* buffer, size_t length, int flags,
                        struct sockaddr* addr, socklen_t* addr_len) {
    const ssize_t ret=__real_recvfrom(fd,buffer,length,flags,addr,addr_len);
    const int saved=errno;
    if (ret>0 && eden_network_audit_active()) {
        char target[80];
        socket_target(fd,addr,addr && addr_len ? *addr_len : 0,target,sizeof(target));
        eden_network_audit_event("launcher","rx",target,(unsigned long long)ret,0);
    }
    errno=saved;
    return ret;
}
