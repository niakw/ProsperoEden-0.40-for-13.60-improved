// SPDX-License-Identifier: GPL-3.0-or-later
// Detailed-logging-only, bounded, buffered audit of network *API* events.
// This does not intercept, reroute, override or configure any system DNS.
#include "network_audit.h"
#include <pthread.h>
#include <stdatomic.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

enum { MAX_PATH=768, MAX_LOG=4*1024*1024, BUFFER_SIZE=32768 };
static pthread_mutex_t audit_mutex = PTHREAD_MUTEX_INITIALIZER;
static atomic_int audit_enabled = ATOMIC_VAR_INIT(0);
static char audit_path[MAX_PATH], audit_old[MAX_PATH + 12];
static char audit_buffer[BUFFER_SIZE];
static FILE* audit_file;
static unsigned long long audit_bytes;
static unsigned audit_line_count;

static void close_locked(void) {
    if (audit_file) {
        (void)fflush(audit_file);
        (void)fclose(audit_file);
        audit_file = NULL;
    }
    audit_bytes=0;
    audit_line_count=0;
}
static void open_locked(void) {
    if (!audit_path[0] || audit_file) return;
    // Before opening a new file, roll over stale logs from past sessions.
    FILE* existing=fopen(audit_path,"rb");
    long old_size=0;
    if (existing) {
        if (!fseek(existing,0,SEEK_END)) old_size=ftell(existing);
        fclose(existing);
    }
    if (old_size < 0) old_size=0;
    if (old_size >= MAX_LOG) {
        (void)remove(audit_old);
        (void)rename(audit_path,audit_old);
        old_size=0;
    }
    audit_file=fopen(audit_path,"ab");
    if (audit_file) {
        (void)setvbuf(audit_file,audit_buffer,_IOFBF,sizeof(audit_buffer));
        audit_bytes=(unsigned long long)old_size;
    }
}
int eden_network_audit_init(const char* path, int detailed) {
    if (!path) return -1;
    const size_t n=strlen(path);
    if (!n || n+6 >= sizeof(audit_path)) return -1;
    pthread_mutex_lock(&audit_mutex);
    if (audit_path[0]) { pthread_mutex_unlock(&audit_mutex); return -1; }
    memcpy(audit_path,path,n+1);
    snprintf(audit_old,sizeof(audit_old),"%s.prev",path);
    // No normal log file when Detailed Logging is OFF. Keep separate crash-*.
    if (!detailed) { (void)remove(audit_path); (void)remove(audit_old); }
    atomic_store_explicit(&audit_enabled,detailed!=0,memory_order_release);
    pthread_mutex_unlock(&audit_mutex);
    return 0;
}
int eden_network_audit_active(void) {
    return atomic_load_explicit(&audit_enabled,memory_order_relaxed);
}
void eden_network_audit_enable(int detailed) {
    pthread_mutex_lock(&audit_mutex);
    if (!detailed) atomic_store_explicit(&audit_enabled,0,memory_order_release);
    if (!detailed) close_locked();
    if (detailed && audit_path[0])
        atomic_store_explicit(&audit_enabled,1,memory_order_release);
    pthread_mutex_unlock(&audit_mutex);
}
static void safe_token(const char* s, char* out, size_t n) {
    size_t i=0;
    if (!s) s="-";
    for (;*s && i+1<n;++s) {
        const unsigned char c=(unsigned char)*s;
        out[i++]=(c>=33 && c<=126 && c!='"' && c!='\\') ? (char)c : '_';
    }
    out[i]=0;
}
void eden_network_audit_event(const char* scope, const char* event,
                              const char* target, unsigned long long bytes,
                              int status) {
    if (!atomic_load_explicit(&audit_enabled,memory_order_acquire)) return;
    pthread_mutex_lock(&audit_mutex);
    if (!atomic_load_explicit(&audit_enabled,memory_order_relaxed)) {
        pthread_mutex_unlock(&audit_mutex);
        return;
    }
    open_locked();
    if (audit_file) {
        char sc[24],kind[28],dst[256];
        safe_token(scope,sc,sizeof(sc));
        safe_token(event,kind,sizeof(kind));
        safe_token(target,dst,sizeof(dst));
        const time_t now=time(NULL);
        const int count=fprintf(audit_file,
            "epoch=%lld scope=%s event=%s target=%s bytes=%llu status=%d\n",
            (long long)now,sc,kind,dst,bytes,status);
        if (count > 0) audit_bytes+=(unsigned)count;
        if (++audit_line_count >= 64) {
            // Buffer output: periodic fflush for forensic usefulness; no
            // fsync-per-packet and no quiet-mode cost.
            (void)fflush(audit_file);
            audit_line_count=0;
        }
        if (audit_bytes >= MAX_LOG) {
            close_locked();
            (void)remove(audit_old);
            (void)rename(audit_path,audit_old);
        }
    }
    pthread_mutex_unlock(&audit_mutex);
}
