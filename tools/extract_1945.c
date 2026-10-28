#include <archive.h>
#include <archive_entry.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int allowed_name(const char *name, const char **out) {
    const char *base = strrchr(name, '/');
    base = base ? base + 1 : name;
    if (!strcmp(base, "1945 I & II (Europe) (En,Fr,De,Es,It).bin") ||
        !strcmp(base, "1945 I & II (Europe) (En,Fr,De,Es,It).cue")) { *out = base; return 1; }
    return 0;
}
int main(int argc, char **argv) {
    if (argc != 3) { fprintf(stderr, "usage: %s archive.7z output-dir\n", argv[0]); return 2; }
    struct archive *a = archive_read_new();
    archive_read_support_filter_all(a); archive_read_support_format_7zip(a);
    if (archive_read_open_filename(a, argv[1], 10240) != ARCHIVE_OK) {
        fprintf(stderr, "open failed: %s\n", archive_error_string(a)); archive_read_free(a); return 1;
    }
    struct archive_entry *entry; int r, extracted = 0, fail = 0;
    char buf[1024*1024];
    while ((r = archive_read_next_header(a, &entry)) == ARCHIVE_OK) {
        const char *name = archive_entry_pathname(entry), *base = NULL;
        la_int64_t expected = archive_entry_size(entry), total = 0;
        if (!allowed_name(name ? name : "", &base) || archive_entry_filetype(entry) != AE_IFREG || expected < 0) {
            fprintf(stderr, "refusing unexpected archive entry: %s\n", name ? name : "(null)"); fail = 1; break;
        }
        char path[4096];
        if (snprintf(path, sizeof(path), "%s/%s", argv[2], base) >= (int)sizeof(path)) { fprintf(stderr,"path too long\n"); fail=1; break; }
        FILE *f = fopen(path, "wb");
        if (!f) { fprintf(stderr,"open output failed: %s\n", strerror(errno)); fail=1; break; }
        for (;;) {
            la_ssize_t n = archive_read_data(a, buf, sizeof(buf));
            if (n == 0) break;
            if (n < 0) { fprintf(stderr,"read failed for %s: %s\n", base, archive_error_string(a)); fail=1; break; }
            if (fwrite(buf, 1, (size_t)n, f) != (size_t)n) { fprintf(stderr,"write failed: %s\n", strerror(errno)); fail=1; break; }
            total += n;
        }
        if (fclose(f) != 0) { fprintf(stderr,"close failed: %s\n", strerror(errno)); fail=1; }
        fprintf(stderr,"EXTRACTED name=%s bytes=%lld expected=%lld status=%s\n", base, (long long)total, (long long)expected, (!fail && total==expected) ? "OK" : "ERROR");
        extracted++;
        if (fail || total != expected) { fail=1; break; }
    }
    if (r != ARCHIVE_EOF && !fail) { fprintf(stderr,"archive read failed: %s\n", archive_error_string(a)); fail=1; }
    archive_read_close(a); archive_read_free(a);
    if (extracted != 2) { fprintf(stderr,"expected exactly 2 files, extracted %d\n", extracted); fail=1; }
    return fail ? 1 : 0;
}
