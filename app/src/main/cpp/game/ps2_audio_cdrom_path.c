#include "ps2_audio_cdrom_path.h"

#include <stdint.h>
#include <string.h>

static char ascii_upper(char value)
{
    if (value >= 'a' && value <= 'z') {
        return (char)(value - ('a' - 'A'));
    }
    return value;
}

int ps2_audio_make_cdrom0_path(const char *input, char *output, size_t output_capacity)
{
    const char *path_start;
    const char *colon;
    const char *semicolon;
    size_t path_length;
    size_t output_length;
    size_t index;
    int needs_separator;

    if (output == NULL || output_capacity == 0u) {
        return 0;
    }
    output[0] = '\0';
    if (input == NULL) {
        return 0;
    }

    colon = strchr(input, ':');
    path_start = colon == NULL ? input : colon + 1;
    semicolon = strchr(path_start, ';');
    path_length = semicolon == NULL ? strlen(path_start) : (size_t)(semicolon - path_start);
    needs_separator = path_length == 0u || (path_start[0] != '/' && path_start[0] != '\\');

    /* "cdrom0:" + optional slash + path + ";1" + NUL. */
    output_length = 7u;
    if (needs_separator != 0) {
        output_length += 1u;
    }
    if (path_length > SIZE_MAX - output_length - 3u) {
        return 0;
    }
    output_length += path_length + 2u;
    if (output_length >= output_capacity) {
        return 0;
    }

    memcpy(output, "cdrom0:", 7u);
    index = 7u;
    if (needs_separator != 0) {
        output[index++] = '\\';
    }
    for (size_t path_index = 0u; path_index < path_length; ++path_index) {
        char value = path_start[path_index];
        if (value == '/') {
            value = '\\';
        }
        output[index++] = ascii_upper(value);
    }
    output[index++] = ';';
    output[index++] = '1';
    output[index] = '\0';
    return 1;
}
