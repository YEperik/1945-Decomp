/* Read-only EDC/ECC verification for XA Mode 2 Form 1 CD-ROM sectors. */
#define _POSIX_C_SOURCE 200809L
#define _FILE_OFFSET_BITS 64
#include <errno.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define SECTOR_SIZE 2352u
#define FINDING_LIMIT 100u
#define EDC_POLY UINT32_C(0xD8018001)

static uint32_t edc_lut[256];
static uint8_t ecc_forward[256];
static uint8_t ecc_backward[256];

typedef struct {
    uint64_t sectors;
    uint64_t eligible;
    uint64_t skipped_non_mode2;
    uint64_t skipped_non_data;
    uint64_t skipped_form2;
    uint64_t sector_errors;
    uint64_t checksum_failing_sectors;
    uint64_t edc_passed, edc_failed;
    uint64_t ecc_p_passed, ecc_p_failed;
    uint64_t ecc_q_passed, ecc_q_failed;
    uint64_t findings;
} report_t;

typedef struct {
    uint64_t lba;
    unsigned edc_failed;
    unsigned ecc_p_failed;
    unsigned ecc_q_failed;
    const char *error;
} finding_t;

static void init_tables(void) {
    for (unsigned i = 0; i < 256; ++i) {
        uint32_t value = i;
        for (unsigned bit = 0; bit < 8; ++bit) {
            value = (value >> 1) ^ ((value & 1u) ? EDC_POLY : 0u);
        }
        edc_lut[i] = value;

        unsigned doubled = i << 1;
        if (doubled & 0x100u) doubled ^= 0x11Du;
        ecc_forward[i] = (uint8_t)doubled;
        ecc_backward[i ^ doubled] = (uint8_t)i;
    }
}

static uint32_t compute_edc(const uint8_t *data, size_t length) {
    uint32_t edc = 0;
    for (size_t i = 0; i < length; ++i) {
        edc = (edc >> 8) ^ edc_lut[(edc ^ data[i]) & 0xFFu];
    }
    return edc;
}

static void compute_ecc(const uint8_t *source, unsigned major_count,
                        unsigned minor_count, unsigned major_mult,
                        unsigned minor_inc, uint8_t *destination) {
    const unsigned size = major_count * minor_count;
    for (unsigned major = 0; major < major_count; ++major) {
        unsigned index = (major >> 1) * major_mult + (major & 1u);
        uint8_t ecc_a = 0;
        uint8_t ecc_b = 0;
        for (unsigned minor = 0; minor < minor_count; ++minor) {
            const uint8_t symbol = source[index];
            index += minor_inc;
            if (index >= size) index -= size;
            ecc_a ^= symbol;
            ecc_b ^= symbol;
            ecc_a = ecc_forward[ecc_a];
        }
        ecc_a = ecc_backward[ecc_forward[ecc_a] ^ ecc_b];
        destination[major] = ecc_a;
        destination[major + major_count] = ecc_a ^ ecc_b;
    }
}

static int verify_sector(const uint8_t *raw, unsigned *edc_bad,
                         unsigned *p_bad, unsigned *q_bad) {
    uint8_t p_source[2064];
    uint8_t q_source[2236];
    uint8_t expected_p[172];
    uint8_t expected_q[104];
    const uint32_t edc = compute_edc(raw + 16, 2056);
    const uint8_t *stored_edc = raw + 2072;
    *edc_bad = stored_edc[0] != (uint8_t)edc ||
               stored_edc[1] != (uint8_t)(edc >> 8) ||
               stored_edc[2] != (uint8_t)(edc >> 16) ||
               stored_edc[3] != (uint8_t)(edc >> 24);

    memcpy(p_source, raw + 12, sizeof(p_source));
    memset(p_source, 0, 4); /* Mode 2 parity treats the address as zero. */
    compute_ecc(p_source, 86, 24, 2, 86, expected_p);
    *p_bad = memcmp(raw + 2076, expected_p, sizeof(expected_p)) != 0;

    memcpy(q_source, raw + 12, sizeof(q_source));
    memset(q_source, 0, 4);
    compute_ecc(q_source, 52, 43, 86, 88, expected_q);
    *q_bad = memcmp(raw + 2248, expected_q, sizeof(expected_q)) != 0;
    return 0;
}

static void record_finding(finding_t *findings, report_t *report,
                           uint64_t lba, unsigned edc_bad, unsigned p_bad,
                           unsigned q_bad, const char *error) {
    if (report->findings >= FINDING_LIMIT) return;
    finding_t *finding = &findings[report->findings++];
    finding->lba = lba;
    finding->edc_failed = edc_bad;
    finding->ecc_p_failed = p_bad;
    finding->ecc_q_failed = q_bad;
    finding->error = error;
}

int main(int argc, char **argv) {
    if (argc != 2) {
        fprintf(stderr, "Usage: %s raw-mode2-image.bin\n", argv[0]);
        return 2;
    }
    FILE *image = fopen(argv[1], "rb");
    if (!image) {
        fprintf(stderr, "Cannot open %s: %s\n", argv[1], strerror(errno));
        return 2;
    }
    if (fseeko(image, 0, SEEK_END) != 0) {
        fprintf(stderr, "Cannot seek input image\n"); fclose(image); return 2;
    }
    const off_t byte_size = ftello(image);
    if (byte_size <= 0 || (uint64_t)byte_size % SECTOR_SIZE != 0) {
        fprintf(stderr, "Input size is not a positive multiple of %u bytes\n", SECTOR_SIZE);
        fclose(image); return 2;
    }
    const uint64_t total_sectors = (uint64_t)byte_size / SECTOR_SIZE;
    if (fseeko(image, 0, SEEK_SET) != 0) {
        fprintf(stderr, "Cannot rewind input image\n"); fclose(image); return 2;
    }

    init_tables();
    report_t report = {0};
    finding_t findings[FINDING_LIMIT];
    uint8_t raw[SECTOR_SIZE];
    report.sectors = total_sectors;
    for (uint64_t lba = 0; lba < total_sectors; ++lba) {
        if (fread(raw, 1, sizeof(raw), image) != sizeof(raw)) {
            fprintf(stderr, "Short read at LBA %" PRIu64 "\n", lba);
            fclose(image); return 2;
        }
        if (raw[15] != 2) {
            ++report.skipped_non_mode2;
            continue;
        }
        const uint8_t submode = raw[18];
        if (!(submode & 0x08u)) {
            ++report.skipped_non_data;
            continue;
        }
        if (submode & 0x20u) {
            ++report.skipped_form2;
            continue;
        }
        if (raw[16] != raw[20] || raw[17] != raw[21] ||
            raw[18] != raw[22] || raw[19] != raw[23]) {
            ++report.sector_errors;
            record_finding(findings, &report, lba, 0, 0, 0, "XA subheader copies differ");
            continue;
        }
        ++report.eligible;
        unsigned edc_bad = 0, p_bad = 0, q_bad = 0;
        (void)verify_sector(raw, &edc_bad, &p_bad, &q_bad);
        if (edc_bad) ++report.edc_failed; else ++report.edc_passed;
        if (p_bad) ++report.ecc_p_failed; else ++report.ecc_p_passed;
        if (q_bad) ++report.ecc_q_failed; else ++report.ecc_q_passed;
        if (edc_bad || p_bad || q_bad) {
            ++report.checksum_failing_sectors;
            record_finding(findings, &report, lba, edc_bad, p_bad, q_bad, NULL);
        }
    }
    fclose(image);

    const uint64_t failures = report.edc_failed + report.ecc_p_failed +
        report.ecc_q_failed + report.sector_errors;
    const int unsupported = report.skipped_non_mode2 > 0 || report.skipped_form2 > 0;
    printf("{\"sector_count\":%" PRIu64 ",", report.sectors);
    printf("\"eligible_data_sector_count\":%" PRIu64 ",", report.eligible);
    printf("\"counts\":{\"form1_data_sectors_checked\":%" PRIu64 ",", report.eligible);
    printf("\"edc_passed\":%" PRIu64 ",\"edc_failed\":%" PRIu64 ",", report.edc_passed, report.edc_failed);
    printf("\"ecc_p_passed\":%" PRIu64 ",\"ecc_p_failed\":%" PRIu64 ",", report.ecc_p_passed, report.ecc_p_failed);
    printf("\"ecc_q_passed\":%" PRIu64 ",\"ecc_q_failed\":%" PRIu64 ",", report.ecc_q_passed, report.ecc_q_failed);
    printf("\"sector_verification_errors\":%" PRIu64 ",", report.sector_errors);
    printf("\"checksum_failing_sectors\":%" PRIu64 ",", report.checksum_failing_sectors);
    printf("\"skipped_non_data\":%" PRIu64 ",\"skipped_form2_unsupported\":%" PRIu64 ",", report.skipped_non_data, report.skipped_form2);
    printf("\"skipped_non_mode2\":%" PRIu64 "},", report.skipped_non_mode2);
    printf("\"failure_count\":%" PRIu64 ",\"finding_count\":%" PRIu64 ",", failures, failures);
    printf("\"findings_truncated_to\":%u,\"findings\":[", FINDING_LIMIT);
    for (uint64_t i = 0; i < report.findings; ++i) {
        const finding_t *finding = &findings[i];
        if (i) putchar(',');
        printf("{\"lba\":%" PRIu64, finding->lba);
        if (finding->error) {
            printf(",\"error\":\"%s\"}", finding->error);
        } else {
            printf(",\"failed_checks\":[");
            unsigned comma = 0;
            if (finding->edc_failed) { printf("\"edc\""); comma = 1; }
            if (finding->ecc_p_failed) { printf("%s\"ecc_p\"", comma ? "," : ""); comma = 1; }
            if (finding->ecc_q_failed) { printf("%s\"ecc_q\"", comma ? "," : ""); }
            printf("]}");
        }
    }
    printf("],\"unsupported_sector_types_present\":%s,", unsupported ? "true" : "false");
    printf("\"all_eligible_sectors_verified\":%s}\n", (!failures && !unsupported) ? "true" : "false");
    return failures == 0 && !unsupported ? 0 : 3;
}
