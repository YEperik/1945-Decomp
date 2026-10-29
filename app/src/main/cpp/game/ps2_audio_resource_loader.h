#ifndef PORT1945_PS2_AUDIO_RESOURCE_LOADER_H
#define PORT1945_PS2_AUDIO_RESOURCE_LOADER_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define PS2_AUDIO_RESOURCE_PATH_CAPACITY 64u
#define PS2_AUDIO_MAX_OPTIONAL_RESOURCES 6u
#define PS2_AUDIO_MAX_SIZE_QUERIES (3u + PS2_AUDIO_MAX_OPTIONAL_RESOURCES)
#define PS2_AUDIO_MAX_SAMPLE_TRANSFERS 2u
#define PS2_AUDIO_RESOURCE_POOL_SIZE 0x8000u
#define PS2_AUDIO_NO_DUPLICATE UINT16_MAX

#define PS2_AUDIO_RPC_QUERY_RESOURCE_SIZE 0x9080u
#define PS2_AUDIO_RPC_TRANSFER_SAMPLE_BANK 0x9060u
#define PS2_AUDIO_RPC_SAMPLE_SETUP_INITIAL 0x9051u
#define PS2_AUDIO_RPC_SAMPLE_SETUP_GROUP 0x9050u

typedef struct Ps2AudioLogicalResource {
    uint16_t resource_index;
    uint32_t table_address;
    const char *sq_relative_path;
    const char *hd_relative_path;
    const char *bd_relative_path;
    uint16_t duplicate_of_index;
} Ps2AudioLogicalResource;

typedef struct Ps2AudioResourcePaths {
    char sq_path[PS2_AUDIO_RESOURCE_PATH_CAPACITY];
    char hd_path[PS2_AUDIO_RESOURCE_PATH_CAPACITY];
    char bd_path[PS2_AUDIO_RESOURCE_PATH_CAPACITY];
} Ps2AudioResourcePaths;

typedef struct Ps2AudioResourceQuery {
    uint32_t command_id;
    uint32_t ee_request_address;
    uint8_t optional;
    char path[PS2_AUDIO_RESOURCE_PATH_CAPACITY];
} Ps2AudioResourceQuery;

typedef struct Ps2AudioSampleTransfer {
    uint32_t transfer_command_id;
    uint32_t ee_request_address;
    uint32_t setup_command_ids[3];
    uint32_t setup_values[3];
    uint8_t is_common_bank;
    char path[PS2_AUDIO_RESOURCE_PATH_CAPACITY];
} Ps2AudioSampleTransfer;

typedef struct Ps2AudioLoadPlan {
    uint16_t resource_index;
    uint8_t allocates_resource_pool;
    size_t size_query_count;
    Ps2AudioResourceQuery size_queries[PS2_AUDIO_MAX_SIZE_QUERIES];
    size_t sample_transfer_count;
    Ps2AudioSampleTransfer sample_transfers[PS2_AUDIO_MAX_SAMPLE_TRANSFERS];
} Ps2AudioLoadPlan;

/* Metadata transcribed from the 61 SQ/HD/BD pointer triplets at 0x0030C0B0. */
size_t ps2_audio_logical_resource_count(void);
const Ps2AudioLogicalResource *ps2_audio_logical_resource_for_index(int32_t index);

/* Build cdrom0:\\SND\\<relative-key>;1 with bounds and key validation. */
int ps2_audio_build_iso_path(const char *relative_key,
                             char *destination,
                             size_t destination_capacity);
int ps2_audio_build_resource_paths(int32_t resource_index,
                                   Ps2AudioResourcePaths *paths);

/*
 * Mirrors the resource request calls visible in FUN_00190FF0 / FUN_00190C20 /
 * FUN_00190F30. optional_resource_paths maps, in order, to EE slots
 * 0x3BB1C0, 0x3BB200, 0x3BB240, 0x3BB280, 0x3BB2C0 and 0x3BB300. Empty optional
 * entries are skipped but do not renumber subsequent EE slots. When
 * initialize_common_sample_bank is nonzero, the shared SE.BD transfer and its
 * setup commands precede the current group's BD transfer. The flag also marks
 * the cold-init path, which calls FUN_00190FF0 and allocates a fresh 0x8000-byte
 * pool. A group-switch plan mirrors FUN_001914C8 and reuses the existing pool.
 *
 * This is a static reference model, not an RPC implementation or audio player.
 */
int ps2_audio_build_load_plan(int32_t resource_index,
                              const char *const optional_resource_paths[PS2_AUDIO_MAX_OPTIONAL_RESOURCES],
                              int initialize_common_sample_bank,
                              Ps2AudioLoadPlan *plan);

/* Explicit wrappers for the two observed call flows: cold initialization and group switch. */
int ps2_audio_build_initial_load_plan(
    int32_t resource_index,
    const char *const optional_resource_paths[PS2_AUDIO_MAX_OPTIONAL_RESOURCES],
    Ps2AudioLoadPlan *plan);
int ps2_audio_build_group_switch_plan(
    int32_t resource_index,
    const char *const optional_resource_paths[PS2_AUDIO_MAX_OPTIONAL_RESOURCES],
    Ps2AudioLoadPlan *plan);

/*
 * Reconstruct the cumulative 0x8000-byte resource pool offsets used by
 * FUN_00190FF0. sizes are in query order: SE.HD, SQ, HD, then six optional
 * resources. Offsets receives the start address of each corresponding item.
 * Returns 1 only if the full pool fits without 32-bit address overflow.
 */
int ps2_audio_calculate_pool_layout(uint32_t base_address,
                                    const uint32_t sizes[PS2_AUDIO_MAX_SIZE_QUERIES],
                                    uint32_t offsets[PS2_AUDIO_MAX_SIZE_QUERIES]);

#ifdef __cplusplus
}
#endif

#endif
