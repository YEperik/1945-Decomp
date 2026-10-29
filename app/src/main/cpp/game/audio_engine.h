#ifndef PORT1945_AUDIO_ENGINE_H
#define PORT1945_AUDIO_ENGINE_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define AUDIO_ENGINE_SAMPLE_RATE 22050u
#define AUDIO_ENGINE_MAX_VOICES 8u

typedef struct AudioVoice {
    double phase;
    double start_frequency;
    double end_frequency;
    float amplitude;
    uint32_t age_frames;
    uint32_t duration_frames;
    uint8_t active;
} AudioVoice;

typedef struct AudioEngine {
    AudioVoice voices[AUDIO_ENGINE_MAX_VOICES];
    uint32_t replacement_index;
} AudioEngine;

void audio_engine_init(AudioEngine *engine);
void audio_engine_render(AudioEngine *engine, uint32_t event_mask,
                         int16_t *output, size_t frames);

#ifdef __cplusplus
}
#endif

#endif
