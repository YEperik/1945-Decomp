#include "audio_engine.h"
#include "game_core.h"

#include <math.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#define PI_D 3.14159265358979323846
#define TWO_PI_D (2.0 * PI_D)
#define PCM_SCALE 32767.0

typedef struct VoicePreset {
    double start_frequency;
    double end_frequency;
    float amplitude;
    float seconds;
} VoicePreset;

static VoicePreset preset_for_event(uint32_t event)
{
    VoicePreset preset;
    preset.start_frequency = 440.0;
    preset.end_frequency = 220.0;
    preset.amplitude = 0.18f;
    preset.seconds = 0.08f;
    switch (event) {
        case GAME_AUDIO_START:
            preset.start_frequency = 260.0;
            preset.end_frequency = 780.0;
            preset.amplitude = 0.20f;
            preset.seconds = 0.22f;
            break;
        case GAME_AUDIO_FIRE:
            preset.start_frequency = 1040.0;
            preset.end_frequency = 520.0;
            preset.amplitude = 0.12f;
            preset.seconds = 0.045f;
            break;
        case GAME_AUDIO_ENEMY_DOWN:
            preset.start_frequency = 520.0;
            preset.end_frequency = 170.0;
            preset.amplitude = 0.22f;
            preset.seconds = 0.13f;
            break;
        case GAME_AUDIO_PLAYER_HIT:
            preset.start_frequency = 210.0;
            preset.end_frequency = 55.0;
            preset.amplitude = 0.32f;
            preset.seconds = 0.24f;
            break;
        case GAME_AUDIO_GAME_OVER:
            preset.start_frequency = 440.0;
            preset.end_frequency = 65.0;
            preset.amplitude = 0.28f;
            preset.seconds = 0.42f;
            break;
        case GAME_AUDIO_PAUSE:
            preset.start_frequency = 660.0;
            preset.end_frequency = 440.0;
            preset.amplitude = 0.10f;
            preset.seconds = 0.07f;
            break;
        default:
            preset.amplitude = 0.0f;
            preset.seconds = 0.0f;
            break;
    }
    return preset;
}

static void start_voice(AudioEngine *engine, uint32_t event)
{
    size_t i;
    size_t target = AUDIO_ENGINE_MAX_VOICES;
    VoicePreset preset = preset_for_event(event);
    AudioVoice *voice;
    if (preset.amplitude <= 0.0f || preset.seconds <= 0.0f) {
        return;
    }
    for (i = 0u; i < AUDIO_ENGINE_MAX_VOICES; ++i) {
        if (engine->voices[i].active == 0u) {
            target = i;
            break;
        }
    }
    if (target == AUDIO_ENGINE_MAX_VOICES) {
        target = engine->replacement_index % AUDIO_ENGINE_MAX_VOICES;
        engine->replacement_index = (engine->replacement_index + 1u) % AUDIO_ENGINE_MAX_VOICES;
    }
    voice = &engine->voices[target];
    voice->phase = 0.0;
    voice->start_frequency = preset.start_frequency;
    voice->end_frequency = preset.end_frequency;
    voice->amplitude = preset.amplitude;
    voice->age_frames = 0u;
    voice->duration_frames = (uint32_t)(preset.seconds * (float)AUDIO_ENGINE_SAMPLE_RATE);
    if (voice->duration_frames == 0u) {
        voice->duration_frames = 1u;
    }
    voice->active = 1u;
}

void audio_engine_init(AudioEngine *engine)
{
    if (engine != NULL) {
        (void)memset(engine, 0, sizeof(*engine));
    }
}

void audio_engine_render(AudioEngine *engine, uint32_t event_mask,
                         int16_t *output, size_t frames)
{
    static const uint32_t events[] = {
        GAME_AUDIO_START, GAME_AUDIO_FIRE, GAME_AUDIO_ENEMY_DOWN,
        GAME_AUDIO_PLAYER_HIT, GAME_AUDIO_GAME_OVER, GAME_AUDIO_PAUSE
    };
    size_t event_index;
    size_t frame;
    if (output == NULL || frames > SIZE_MAX / sizeof(*output)) {
        /* The caller's capacity is unknown, but the byte-size calculation must not wrap. */
        return;
    }
    if (engine == NULL) {
        (void)memset(output, 0, frames * sizeof(*output));
        return;
    }
    for (event_index = 0u; event_index < sizeof(events) / sizeof(events[0]); ++event_index) {
        if ((event_mask & events[event_index]) != 0u) {
            start_voice(engine, events[event_index]);
        }
    }

    for (frame = 0u; frame < frames; ++frame) {
        double mixed = 0.0;
        size_t voice_index;
        for (voice_index = 0u; voice_index < AUDIO_ENGINE_MAX_VOICES; ++voice_index) {
            AudioVoice *voice = &engine->voices[voice_index];
            double progress;
            double frequency;
            double envelope;
            if (voice->active == 0u) {
                continue;
            }
            progress = (double)voice->age_frames / (double)voice->duration_frames;
            frequency = voice->start_frequency +
                (voice->end_frequency - voice->start_frequency) * progress;
            envelope = (1.0 - progress);
            if (envelope < 0.0) {
                envelope = 0.0;
            }
            mixed += sin(voice->phase) * (double)voice->amplitude * envelope;
            voice->phase += TWO_PI_D * frequency / (double)AUDIO_ENGINE_SAMPLE_RATE;
            if (voice->phase >= TWO_PI_D) {
                voice->phase -= TWO_PI_D * floor(voice->phase / TWO_PI_D);
            }
            voice->age_frames += 1u;
            if (voice->age_frames >= voice->duration_frames) {
                voice->active = 0u;
            }
        }
        if (mixed > 1.0) mixed = 1.0;
        if (mixed < -1.0) mixed = -1.0;
        output[frame] = (int16_t)(mixed * PCM_SCALE);
    }
}
