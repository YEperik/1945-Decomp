#include <archive.h>
#include <archive_entry.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>

int main(int argc, char **argv) {
    if (argc != 2) { fprintf(stderr, "usage: %s archive.7z\n", argv[0]); return 2; }
    struct archive *a = archive_read_new();
    if (!a) { fprintf(stderr, "archive_read_new failed\n"); return 2; }
    archive_read_support_filter_all(a);
    archive_read_support_format_7zip(a);
    if (archive_read_open_filename(a, argv[1], 10240) != ARCHIVE_OK) {
        fprintf(stderr, "open failed: %s\n", archive_error_string(a));
        archive_read_free(a); return 1;
    }
    struct archive_entry *entry;
    int64_t count = 0, total_known = 0, unknown_sizes = 0;
    int r;
    while ((r = archive_read_next_header(a, &entry)) == ARCHIVE_OK) {
        const char *name = archive_entry_pathname(entry);
        la_int64_t size = archive_entry_size(entry);
        mode_t type = archive_entry_filetype(entry);
        const char *kind = type == AE_IFDIR ? "dir" : type == AE_IFREG ? "file" : type == AE_IFLNK ? "symlink" : "other";
        printf("%s\t%" PRId64 "\t%s\t%s\n", kind, (int64_t)size, size >= 0 ? "known" : "unknown", name ? name : "(null)");
        count++;
        if (size >= 0) total_known += (int64_t)size; else unknown_sizes++;
        if (archive_read_data_skip(a) != ARCHIVE_OK) {
            fprintf(stderr, "data skip warning for %s: %s\n", name ? name : "(null)", archive_error_string(a));
        }
    }
    if (r != ARCHIVE_EOF) {
        fprintf(stderr, "iteration ended with status %d: %s\n", r, archive_error_string(a));
    }
    fprintf(stderr, "SUMMARY entries=%" PRId64 " known_uncompressed_bytes=%" PRId64 " unknown_sizes=%" PRId64 " status=%s\n", count, total_known, unknown_sizes, r == ARCHIVE_EOF ? "EOF" : "ERROR");
    int exit_status = r == ARCHIVE_EOF ? 0 : 1;
    archive_read_close(a); archive_read_free(a); return exit_status;
}
