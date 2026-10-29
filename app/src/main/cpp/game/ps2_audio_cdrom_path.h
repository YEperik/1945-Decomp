#ifndef PORT1945_PS2_AUDIO_CDROM_PATH_H
#define PORT1945_PS2_AUDIO_CDROM_PATH_H

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Model of the observed FUN_001869A0 path normalization routine.
 * Returns 1 on success and 0 on invalid arguments / insufficient output space.
 * On failure, output[0] is cleared when an output buffer is available.
 */
int ps2_audio_make_cdrom0_path(const char *input, char *output, size_t output_capacity);

#ifdef __cplusplus
}
#endif

#endif
