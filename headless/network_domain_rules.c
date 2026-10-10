// SPDX-License-Identifier: GPL-3.0-or-later
// Small C11 immutable runtime policy: no heap allocation, DNS, sockets or
// logging on the per-lookup path. Caller loads once before network startup.
#include "network_domain_rules.h"
#include <ctype.h>
#include <stdatomic.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>

enum { MAX_RULES = 512, MAX_NAME = 255 };
static char rules[MAX_RULES][MAX_NAME + 1];
static unsigned rule_count;
static atomic_int ready = ATOMIC_VAR_INIT(0);

static int is_valid_name(const char* name, int wildcard) {
    size_t label = 0;
    for (const unsigned char* p = (const unsigned char*)name; *p; ++p) {
        const unsigned char c = *p;
        if (c == '.') {
            if (!label) return 0;
            label = 0;
        } else if ((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') ||
                   c == '-' || (wildcard && c == '*')) {
            ++label;
        } else {
            return 0;
        }
    }
    return label != 0;
}

static int canonical_name(const char* raw, char* output, int wildcard) {
    if (!raw) return 0;
    size_t n = 0;
    while (*raw && n <= MAX_NAME) {
        const unsigned char c = (unsigned char)*raw++;
        // Accept escaped dots in supplied host rules (gw\\.hac...) as '.'.
        if (wildcard && c == '\\' && *raw == '.') {
            ++raw;
            output[n++] = '.';
        } else if (c < 128) {
            output[n++] = (char)tolower(c);
        } else {
            return 0;
        }
    }
    if (n > MAX_NAME || *raw) return 0;
    if (n && output[n-1] == '.') --n; // absolute DNS name with final dot
    output[n] = '\0';
    return n && is_valid_name(output, wildcard);
}

// Anchored glob: '*' is zero or more characters INSIDE a single DNS label.
// Iterate hostname suffixes separately to grant implicit subdomain matching.
static int glob_label_safe(const char* host, const char* pattern) {
    const char* star = NULL;
    const char* retry = NULL;
    while (*host) {
        if (*pattern == '*') {
            star = pattern++;
            retry = host;
        } else if (*pattern == *host) {
            ++pattern;
            ++host;
        } else if (star && *retry && *retry != '.') {
            pattern = star + 1;
            host = ++retry;
        } else {
            return 0;
        }
    }
    while (*pattern == '*') ++pattern;
    return *pattern == '\0';
}

int eden_network_filter_load(const char* path) {
    // Never silently replace an in-use immutable table.
    if (atomic_load_explicit(&ready, memory_order_acquire)) return -1;
    if (!path) return -1;
    FILE* f = fopen(path, "rb");
    if (!f) return -1;
    unsigned count = 0;
    char line[512];
    int valid = 1;
    while (fgets(line, sizeof(line), f)) {
        if (!strchr(line, '\n') && !feof(f)) { valid = 0; break; }
        char* p = line;
        while (*p == ' ' || *p == '\t') ++p;
        if (!*p || *p == '#' || *p == '\r' || *p == '\n') continue;
        char* end = p;
        while (*end && *end != '#' && *end != '\n' && *end != '\r' &&
               *end != ' ' && *end != '\t') ++end;
        *end = '\0';
        if (count >= MAX_RULES || !canonical_name(p, rules[count], 1)) {
            valid = 0;
            break;
        }
        ++count;
    }
    if (ferror(f)) valid = 0;
    fclose(f);
    if (!valid || !count) { rule_count = 0; return -1; }
    rule_count = count;
    atomic_store_explicit(&ready, 1, memory_order_release);
    return 0;
}

unsigned eden_network_filter_count(void) {
    return atomic_load_explicit(&ready, memory_order_acquire) ? rule_count : 0;
}

int eden_network_host_blocked(const char* host) {
    // Even failure to read the packaged list must never bypass the policy.
    if (!atomic_load_explicit(&ready, memory_order_acquire)) return 1;
    char canonical[MAX_NAME + 1];
    if (!canonical_name(host, canonical, 0)) return 1;
    for (const char* suffix = canonical; ; ) {
        for (unsigned i = 0; i < rule_count; ++i)
            if (glob_label_safe(suffix, rules[i])) return 1;
        const char* dot = strchr(suffix, '.');
        if (!dot) break;
        suffix = dot + 1;
    }
    return 0;
}
