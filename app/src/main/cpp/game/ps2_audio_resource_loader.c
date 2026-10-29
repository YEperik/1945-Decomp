#include "ps2_audio_resource_loader.h"

#include <limits.h>
#include <stdio.h>
#include <string.h>

/* Generated from evidence/ghidra_audio_logical_resource_catalog.csv. */
static const Ps2AudioLogicalResource k_resources[] = {
    {0u, 0x0030C0B0u, "G00\\M_01_VB.SQ", "G00\\M_01_VB.HD", "G00\\M_01_VB.BD", PS2_AUDIO_NO_DUPLICATE},
    {1u, 0x0030C0BCu, "G00\\M_01_VB.SQ", "G00\\M_01_VB.HD", "G00\\M_01_VB.BD", 0u},
    {2u, 0x0030C0C8u, "G20\\G26.SQ", "G20\\G26.HD", "G20\\G26.BD", PS2_AUDIO_NO_DUPLICATE},
    {3u, 0x0030C0D4u, "G00\\G02.SQ", "G00\\G02.HD", "G00\\G02.BD", PS2_AUDIO_NO_DUPLICATE},
    {4u, 0x0030C0E0u, "G00\\G03.SQ", "G00\\G03.HD", "G00\\G03.BD", PS2_AUDIO_NO_DUPLICATE},
    {5u, 0x0030C0ECu, "G00\\G04.SQ", "G00\\G04.HD", "G00\\G04.BD", PS2_AUDIO_NO_DUPLICATE},
    {6u, 0x0030C0F8u, "G00\\G05.SQ", "G00\\G05.HD", "G00\\G05.BD", PS2_AUDIO_NO_DUPLICATE},
    {7u, 0x0030C104u, "G00\\G06.SQ", "G00\\G06.HD", "G00\\G06.BD", PS2_AUDIO_NO_DUPLICATE},
    {8u, 0x0030C110u, "G00\\G07.SQ", "G00\\G07.HD", "G00\\G07.BD", PS2_AUDIO_NO_DUPLICATE},
    {9u, 0x0030C11Cu, "G10\\G14.SQ", "G10\\G14.HD", "G10\\G14.BD", PS2_AUDIO_NO_DUPLICATE},
    {10u, 0x0030C128u, "G00\\G08.SQ", "G00\\G08.HD", "G00\\G08.BD", PS2_AUDIO_NO_DUPLICATE},
    {11u, 0x0030C134u, "G00\\G09.SQ", "G00\\G09.HD", "G00\\G09.BD", PS2_AUDIO_NO_DUPLICATE},
    {12u, 0x0030C140u, "G30\\G35.SQ", "G30\\G35.HD", "G30\\G35.BD", PS2_AUDIO_NO_DUPLICATE},
    {13u, 0x0030C14Cu, "G10\\G10.SQ", "G10\\G10.HD", "G10\\G10.BD", PS2_AUDIO_NO_DUPLICATE},
    {14u, 0x0030C158u, "G10\\G11.SQ", "G10\\G11.HD", "G10\\G11.BD", PS2_AUDIO_NO_DUPLICATE},
    {15u, 0x0030C164u, "G30\\G34.SQ", "G30\\G34.HD", "G30\\G34.BD", PS2_AUDIO_NO_DUPLICATE},
    {16u, 0x0030C170u, "G10\\G12.SQ", "G10\\G12.HD", "G10\\G12.BD", PS2_AUDIO_NO_DUPLICATE},
    {17u, 0x0030C17Cu, "G10\\G13.SQ", "G10\\G13.HD", "G10\\G13.BD", PS2_AUDIO_NO_DUPLICATE},
    {18u, 0x0030C188u, "G50\\G57.SQ", "G50\\G57.HD", "G50\\G57.BD", PS2_AUDIO_NO_DUPLICATE},
    {19u, 0x0030C194u, "G20\\G29.SQ", "G20\\G29.HD", "G20\\G29.BD", PS2_AUDIO_NO_DUPLICATE},
    {20u, 0x0030C1A0u, "G30\\G31.SQ", "G30\\G31.HD", "G30\\G31.BD", PS2_AUDIO_NO_DUPLICATE},
    {21u, 0x0030C1ACu, "G30\\G38.SQ", "G30\\G38.HD", "G30\\G38.BD", PS2_AUDIO_NO_DUPLICATE},
    {22u, 0x0030C1B8u, "G30\\G39.SQ", "G30\\G39.HD", "G30\\G39.BD", PS2_AUDIO_NO_DUPLICATE},
    {23u, 0x0030C1C4u, "G40\\G40.SQ", "G40\\G40.HD", "G40\\G40.BD", PS2_AUDIO_NO_DUPLICATE},
    {24u, 0x0030C1D0u, "G30\\G32.SQ", "G30\\G32.HD", "G30\\G32.BD", PS2_AUDIO_NO_DUPLICATE},
    {25u, 0x0030C1DCu, "G20\\G22.SQ", "G20\\G22.HD", "G20\\G22.BD", PS2_AUDIO_NO_DUPLICATE},
    {26u, 0x0030C1E8u, "G10\\G19.SQ", "G10\\G19.HD", "G10\\G19.BD", PS2_AUDIO_NO_DUPLICATE},
    {27u, 0x0030C1F4u, "G10\\G15.SQ", "G10\\G15.HD", "G10\\G15.BD", PS2_AUDIO_NO_DUPLICATE},
    {28u, 0x0030C200u, "G30\\G33.SQ", "G30\\G33.HD", "G30\\G33.BD", PS2_AUDIO_NO_DUPLICATE},
    {29u, 0x0030C20Cu, "G20\\G20.SQ", "G20\\G20.HD", "G20\\G20.BD", PS2_AUDIO_NO_DUPLICATE},
    {30u, 0x0030C218u, "G10\\G17.SQ", "G10\\G17.HD", "G10\\G17.BD", PS2_AUDIO_NO_DUPLICATE},
    {31u, 0x0030C224u, "G20\\G25.SQ", "G20\\G25.HD", "G20\\G25.BD", PS2_AUDIO_NO_DUPLICATE},
    {32u, 0x0030C230u, "G40\\G47.SQ", "G40\\G47.HD", "G40\\G47.BD", PS2_AUDIO_NO_DUPLICATE},
    {33u, 0x0030C23Cu, "G40\\G46.SQ", "G40\\G46.HD", "G40\\G46.BD", PS2_AUDIO_NO_DUPLICATE},
    {34u, 0x0030C248u, "G40\\G44.SQ", "G40\\G44.HD", "G40\\G44.BD", PS2_AUDIO_NO_DUPLICATE},
    {35u, 0x0030C254u, "G40\\G43.SQ", "G40\\G43.HD", "G40\\G43.BD", PS2_AUDIO_NO_DUPLICATE},
    {36u, 0x0030C260u, "G40\\G45.SQ", "G40\\G45.HD", "G40\\G45.BD", PS2_AUDIO_NO_DUPLICATE},
    {37u, 0x0030C26Cu, "G30\\M_37_VB.SQ", "G30\\M_37_VB.HD", "G30\\M_37_VB.BD", PS2_AUDIO_NO_DUPLICATE},
    {38u, 0x0030C278u, "G30\\M_38_VB.SQ", "G30\\M_38_VB.HD", "G30\\M_38_VB.BD", PS2_AUDIO_NO_DUPLICATE},
    {39u, 0x0030C284u, "G40\\G42.SQ", "G40\\G42.HD", "G40\\G42.BD", PS2_AUDIO_NO_DUPLICATE},
    {40u, 0x0030C290u, "G40\\G49.SQ", "G40\\G49.HD", "G40\\G49.BD", PS2_AUDIO_NO_DUPLICATE},
    {41u, 0x0030C29Cu, "G10\\G16.SQ", "G10\\G16.HD", "G10\\G16.BD", PS2_AUDIO_NO_DUPLICATE},
    {42u, 0x0030C2A8u, "G30\\G36.SQ", "G30\\G36.HD", "G30\\G36.BD", PS2_AUDIO_NO_DUPLICATE},
    {43u, 0x0030C2B4u, "G50\\G50.SQ", "G50\\G50.HD", "G50\\G50.BD", PS2_AUDIO_NO_DUPLICATE},
    {44u, 0x0030C2C0u, "G50\\G53.SQ", "G50\\G53.HD", "G50\\G53.BD", PS2_AUDIO_NO_DUPLICATE},
    {45u, 0x0030C2CCu, "G40\\G48.SQ", "G40\\G48.HD", "G40\\G48.BD", PS2_AUDIO_NO_DUPLICATE},
    {46u, 0x0030C2D8u, "G20\\G23.SQ", "G20\\G23.HD", "G20\\G23.BD", PS2_AUDIO_NO_DUPLICATE},
    {47u, 0x0030C2E4u, "G20\\G24.SQ", "G20\\G24.HD", "G20\\G24.BD", PS2_AUDIO_NO_DUPLICATE},
    {48u, 0x0030C2F0u, "G20\\G27.SQ", "G20\\G27.HD", "G20\\G27.BD", PS2_AUDIO_NO_DUPLICATE},
    {49u, 0x0030C2FCu, "G30\\G30.SQ", "G30\\G30.HD", "G30\\G30.BD", PS2_AUDIO_NO_DUPLICATE},
    {50u, 0x0030C308u, "G30\\G37.SQ", "G30\\G37.HD", "G30\\G37.BD", PS2_AUDIO_NO_DUPLICATE},
    {51u, 0x0030C314u, "G50\\G51.SQ", "G50\\G51.HD", "G50\\G51.BD", PS2_AUDIO_NO_DUPLICATE},
    {52u, 0x0030C320u, "G20\\G28.SQ", "G20\\G28.HD", "G20\\G28.BD", PS2_AUDIO_NO_DUPLICATE},
    {53u, 0x0030C32Cu, "G50\\G54.SQ", "G50\\G54.HD", "G50\\G54.BD", PS2_AUDIO_NO_DUPLICATE},
    {54u, 0x0030C338u, "ETC\\TAIKO.SQ", "ETC\\TAIKO.HD", "ETC\\TAIKO.BD", PS2_AUDIO_NO_DUPLICATE},
    {55u, 0x0030C344u, "G20\\G21.SQ", "G20\\G21.HD", "G20\\G21.BD", PS2_AUDIO_NO_DUPLICATE},
    {56u, 0x0030C350u, "G50\\G55.SQ", "G50\\G55.HD", "G50\\G55.BD", PS2_AUDIO_NO_DUPLICATE},
    {57u, 0x0030C35Cu, "G40\\G41.SQ", "G40\\G41.HD", "G40\\G41.BD", PS2_AUDIO_NO_DUPLICATE},
    {58u, 0x0030C368u, "G10\\G18.SQ", "G10\\G18.HD", "G10\\G18.BD", PS2_AUDIO_NO_DUPLICATE},
    {59u, 0x0030C374u, "G50\\G56.SQ", "G50\\G56.HD", "G50\\G56.BD", PS2_AUDIO_NO_DUPLICATE},
    {60u, 0x0030C380u, "G50\\G57.SQ", "G50\\G57.HD", "G50\\G57.BD", 18u},
};

#define PS2_AUDIO_ARRAY_COUNT(array) (sizeof(array) / sizeof((array)[0]))

size_t ps2_audio_logical_resource_count(void)
{
    return PS2_AUDIO_ARRAY_COUNT(k_resources);
}

const Ps2AudioLogicalResource *ps2_audio_logical_resource_for_index(int32_t index)
{
    if (index < 0 || (uint32_t)index >= (uint32_t)PS2_AUDIO_ARRAY_COUNT(k_resources)) {
        return NULL;
    }
    return &k_resources[(size_t)index];
}

static int is_ascii_alphanumeric(char value)
{
    return (value >= 'a' && value <= 'z') ||
           (value >= 'A' && value <= 'Z') ||
           (value >= '0' && value <= '9');
}

static int valid_relative_key(const char *key)
{
    size_t index = 0u;
    size_t filename_start;
    size_t dot_index;
    size_t length;
    int valid_directory;

    if (key == NULL) {
        return 0;
    }
    length = strlen(key);
    /* The source table contains Gdd\... entries and the explicit ETC\TAIKO entry. */
    if (length < 9u) {
        return 0;
    }
    valid_directory = key[0] == 'G' && key[1] >= '0' && key[1] <= '9' &&
                      key[2] >= '0' && key[2] <= '9' && key[3] == '\\';
    if (!valid_directory && strncmp(key, "ETC\\", 4u) != 0) {
        return 0;
    }
    filename_start = 4u;
    dot_index = length;
    for (index = filename_start; index < length; ++index) {
        if (key[index] == '\\' || key[index] == '/' || key[index] == ':') {
            return 0;
        }
        if (key[index] == '.') {
            if (dot_index != length) {
                return 0;
            }
            dot_index = index;
        } else if (!is_ascii_alphanumeric(key[index]) && key[index] != '_') {
            return 0;
        }
    }
    if (dot_index <= filename_start || dot_index + 3u != length) {
        return 0;
    }
    return (key[dot_index + 1u] == 'S' && key[dot_index + 2u] == 'Q') ||
           (key[dot_index + 1u] == 'H' && key[dot_index + 2u] == 'D') ||
           (key[dot_index + 1u] == 'B' && key[dot_index + 2u] == 'D');
}

int ps2_audio_build_iso_path(const char *relative_key, char *destination,
                             size_t destination_capacity)
{
    static const char prefix[] = "cdrom0:\\SND\\";
    static const char suffix[] = ";1";
    size_t required;
    int written;

    if (destination == NULL || destination_capacity == 0u) {
        return 0;
    }
    destination[0] = '\0';
    if (!valid_relative_key(relative_key)) {
        return 0;
    }
    required = sizeof(prefix) - 1u + strlen(relative_key) + sizeof(suffix);
    if (required > destination_capacity) {
        return 0;
    }
    written = snprintf(destination, destination_capacity, "%s%s%s", prefix, relative_key, suffix);
    if (written < 0 || (size_t)written >= destination_capacity) {
        destination[0] = '\0';
        return 0;
    }
    return 1;
}

static int build_one_path(const char *key, char *destination, size_t capacity)
{
    return ps2_audio_build_iso_path(key, destination, capacity);
}

int ps2_audio_build_resource_paths(int32_t resource_index, Ps2AudioResourcePaths *paths)
{
    const Ps2AudioLogicalResource *resource;

    if (paths == NULL) {
        return 0;
    }
    memset(paths, 0, sizeof(*paths));
    resource = ps2_audio_logical_resource_for_index(resource_index);
    if (resource == NULL ||
        !build_one_path(resource->sq_relative_path, paths->sq_path, sizeof(paths->sq_path)) ||
        !build_one_path(resource->hd_relative_path, paths->hd_path, sizeof(paths->hd_path)) ||
        !build_one_path(resource->bd_relative_path, paths->bd_path, sizeof(paths->bd_path))) {
        memset(paths, 0, sizeof(*paths));
        return 0;
    }
    return 1;
}

static int copy_full_snd1_path(const char *source, char *destination, size_t capacity)
{
    static const char prefix[] = "cdrom0:\\SND1\\";
    const char *filename;
    size_t length;
    size_t stem_length;
    size_t i;

    if (source == NULL || destination == NULL || capacity == 0u) {
        return 0;
    }
    destination[0] = '\0';
    length = strlen(source);
    if (length < sizeof(prefix) + 4u || strncmp(source, prefix, sizeof(prefix) - 1u) != 0 ||
        strcmp(source + length - 2u, ";1") != 0 || strchr(source, '/') != NULL ||
        strstr(source, "..") != NULL) {
        return 0;
    }
    filename = source + sizeof(prefix) - 1u;
    if (strchr(filename, '\\') != NULL) {
        return 0;
    }
    if (length >= 5u &&
        (strcmp(source + length - 5u, ".SQ;1") == 0 ||
         strcmp(source + length - 5u, ".HD;1") == 0 ||
         strcmp(source + length - 5u, ".BD;1") == 0)) {
        stem_length = length - (sizeof(prefix) - 1u) - 5u;
    } else {
        return 0;
    }
    if (stem_length == 0u) {
        return 0;
    }
    for (i = 0u; i < stem_length; ++i) {
        if (!is_ascii_alphanumeric(filename[i]) && filename[i] != '_') {
            return 0;
        }
    }
    if (length + 1u > capacity) {
        return 0;
    }
    memcpy(destination, source, length + 1u);
    return 1;
}

static int push_size_query(Ps2AudioLoadPlan *plan, uint32_t address, const char *path, int optional)
{
    Ps2AudioResourceQuery *query;
    size_t length;

    if (plan == NULL || path == NULL || path[0] == '\0') {
        return optional;
    }
    if (plan->size_query_count >= PS2_AUDIO_MAX_SIZE_QUERIES) {
        return 0;
    }
    length = strlen(path);
    if (length >= PS2_AUDIO_RESOURCE_PATH_CAPACITY) {
        return 0;
    }
    query = &plan->size_queries[plan->size_query_count];
    memset(query, 0, sizeof(*query));
    query->command_id = PS2_AUDIO_RPC_QUERY_RESOURCE_SIZE;
    query->ee_request_address = address;
    query->optional = (uint8_t)(optional != 0);
    memcpy(query->path, path, length + 1u);
    plan->size_query_count += 1u;
    return 1;
}

static int push_sample_transfer(Ps2AudioLoadPlan *plan, const char *path, int common_bank)
{
    Ps2AudioSampleTransfer *transfer;
    size_t length;

    if (plan == NULL || path == NULL || path[0] == '\0' ||
        plan->sample_transfer_count >= PS2_AUDIO_MAX_SAMPLE_TRANSFERS) {
        return 0;
    }
    length = strlen(path);
    if (length >= PS2_AUDIO_RESOURCE_PATH_CAPACITY) {
        return 0;
    }
    transfer = &plan->sample_transfers[plan->sample_transfer_count];
    memset(transfer, 0, sizeof(*transfer));
    transfer->transfer_command_id = PS2_AUDIO_RPC_TRANSFER_SAMPLE_BANK;
    transfer->ee_request_address = 0x003BB080u;
    transfer->is_common_bank = (uint8_t)(common_bank != 0);
    if (common_bank != 0) {
        transfer->setup_command_ids[0] = PS2_AUDIO_RPC_SAMPLE_SETUP_INITIAL;
        transfer->setup_values[0] = 0x003BB080u;
        transfer->setup_command_ids[1] = 0x00A1u;
        transfer->setup_values[1] = 0x1840u;
        transfer->setup_command_ids[2] = 0x00B1u;
        transfer->setup_values[2] = 0x100u;
    } else {
        transfer->setup_command_ids[0] = PS2_AUDIO_RPC_SAMPLE_SETUP_GROUP;
        transfer->setup_values[0] = 0x003BB080u;
        transfer->setup_command_ids[1] = 0x00A0u;
        transfer->setup_values[1] = 0x2010u;
        transfer->setup_command_ids[2] = 0x00B0u;
        transfer->setup_values[2] = 0x80u;
    }
    memcpy(transfer->path, path, length + 1u);
    plan->sample_transfer_count += 1u;
    return 1;
}

int ps2_audio_build_load_plan(int32_t resource_index,
                              const char *const optional_resource_paths[PS2_AUDIO_MAX_OPTIONAL_RESOURCES],
                              int initialize_common_sample_bank, Ps2AudioLoadPlan *plan)
{
    static const uint32_t optional_slot_addresses[PS2_AUDIO_MAX_OPTIONAL_RESOURCES] = {
        0x003BB1C0u, 0x003BB200u, 0x003BB240u, 0x003BB280u, 0x003BB2C0u, 0x003BB300u
    };
    static const char common_voice_header[] = "cdrom0:\\SND1\\SE.HD;1";
    static const char common_sample_bank[] = "cdrom0:\\SND1\\SE.BD;1";
    Ps2AudioResourcePaths paths;
    char common_header_path[PS2_AUDIO_RESOURCE_PATH_CAPACITY];
    char common_bank_path[PS2_AUDIO_RESOURCE_PATH_CAPACITY];
    size_t i;

    if (plan == NULL) {
        return 0;
    }
    memset(plan, 0, sizeof(*plan));
    if (!ps2_audio_build_resource_paths(resource_index, &paths) ||
        !copy_full_snd1_path(common_voice_header, common_header_path, sizeof(common_header_path)) ||
        !copy_full_snd1_path(common_sample_bank, common_bank_path, sizeof(common_bank_path))) {
        return 0;
    }
    plan->resource_index = (uint16_t)resource_index;
    plan->allocates_resource_pool = (uint8_t)(initialize_common_sample_bank != 0);
    if (!push_size_query(plan, 0x003BB180u, common_header_path, 0) ||
        !push_size_query(plan, 0x0030C3C0u, paths.sq_path, 0) ||
        !push_size_query(plan, 0x003BB100u, paths.hd_path, 0)) {
        memset(plan, 0, sizeof(*plan));
        return 0;
    }
    for (i = 0u; i < PS2_AUDIO_MAX_OPTIONAL_RESOURCES; ++i) {
        const char *optional_path = optional_resource_paths == NULL ? NULL : optional_resource_paths[i];
        char safe_path[PS2_AUDIO_RESOURCE_PATH_CAPACITY];

        if (optional_path == NULL || optional_path[0] == '\0') {
            continue;
        }
        if (!copy_full_snd1_path(optional_path, safe_path, sizeof(safe_path)) ||
            !push_size_query(plan, optional_slot_addresses[i], safe_path, 1)) {
            memset(plan, 0, sizeof(*plan));
            return 0;
        }
    }
    if (initialize_common_sample_bank != 0 && !push_sample_transfer(plan, common_bank_path, 1)) {
        memset(plan, 0, sizeof(*plan));
        return 0;
    }
    if (!push_sample_transfer(plan, paths.bd_path, 0)) {
        memset(plan, 0, sizeof(*plan));
        return 0;
    }
    return 1;
}

int ps2_audio_build_initial_load_plan(
    int32_t resource_index,
    const char *const optional_resource_paths[PS2_AUDIO_MAX_OPTIONAL_RESOURCES],
    Ps2AudioLoadPlan *plan)
{
    return ps2_audio_build_load_plan(resource_index, optional_resource_paths, 1, plan);
}

int ps2_audio_build_group_switch_plan(
    int32_t resource_index,
    const char *const optional_resource_paths[PS2_AUDIO_MAX_OPTIONAL_RESOURCES],
    Ps2AudioLoadPlan *plan)
{
    return ps2_audio_build_load_plan(resource_index, optional_resource_paths, 0, plan);
}

int ps2_audio_calculate_pool_layout(uint32_t base_address,
                                    const uint32_t sizes[PS2_AUDIO_MAX_SIZE_QUERIES],
                                    uint32_t offsets[PS2_AUDIO_MAX_SIZE_QUERIES])
{
    uint32_t temporary_offsets[PS2_AUDIO_MAX_SIZE_QUERIES];
    uint64_t cursor;
    size_t i;

    if (sizes == NULL || offsets == NULL) {
        return 0;
    }
    cursor = (uint64_t)base_address;
    for (i = 0u; i < PS2_AUDIO_MAX_SIZE_QUERIES; ++i) {
        uint64_t relative;

        relative = cursor - (uint64_t)base_address;
        if (relative > (uint64_t)PS2_AUDIO_RESOURCE_POOL_SIZE ||
            cursor > (uint64_t)UINT32_MAX) {
            return 0;
        }
        temporary_offsets[i] = (uint32_t)cursor;
        cursor += (uint64_t)sizes[i];
    }
    if (cursor > (uint64_t)UINT32_MAX ||
        cursor - (uint64_t)base_address > (uint64_t)PS2_AUDIO_RESOURCE_POOL_SIZE) {
        return 0;
    }
    memcpy(offsets, temporary_offsets, sizeof(temporary_offsets));
    return 1;
}
