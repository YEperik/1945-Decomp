#ifndef ANDROID_GAMEPAD_ADAPTER_H
#define ANDROID_GAMEPAD_ADAPTER_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define AGP_MAX_KEY_BINDINGS 32u
#define AGP_MAX_HAT_BINDINGS 4u
#define AGP_AXIS_COUNT 4u

/* Numeric target channels, deliberately not named left/right stick. */
typedef enum AgpAxisTarget {
    AGP_AXIS_A_X = 0,
    AGP_AXIS_A_Y = 1,
    AGP_AXIS_B_X = 2,
    AGP_AXIS_B_Y = 3
} AgpAxisTarget;

typedef struct AgpKeyBinding {
    int32_t android_key_code;
    uint16_t output_mask;
    bool down;
} AgpKeyBinding;

typedef struct AgpHatBinding {
    int32_t android_axis_code;
    uint16_t negative_mask;
    uint16_t positive_mask;
    float value;
    bool configured;
} AgpHatBinding;

typedef struct AndroidGamepadAdapter {
    AgpKeyBinding keys[AGP_MAX_KEY_BINDINGS];
    size_t key_count;
    int32_t axis_code[AGP_AXIS_COUNT];
    bool axis_bound[AGP_AXIS_COUNT];
    float axis_value[AGP_AXIS_COUNT];
    AgpHatBinding hats[AGP_MAX_HAT_BINDINGS];
    size_t hat_count;
    bool connected;
} AndroidGamepadAdapter;

typedef struct AndroidGamepadSample {
    uint16_t buttons_mask; /* Active-high output mask; meaning is config-defined. */
    int16_t axes[AGP_AXIS_COUNT]; /* Signed, centered values in [-128, 127]. */
    bool connected;
} AndroidGamepadSample;

void agp_init(AndroidGamepadAdapter *adapter);
void agp_set_connected(AndroidGamepadAdapter *adapter, bool connected);

/* Bind Android event codes to numeric game bits; no semantic defaults are assumed. */
bool agp_bind_key(AndroidGamepadAdapter *adapter,
                  int32_t android_key_code,
                  uint16_t output_mask);
bool agp_bind_axis(AndroidGamepadAdapter *adapter,
                   int32_t android_axis_code,
                   AgpAxisTarget target);
/* Use for Android hat axes when they should produce digital game bits. */
bool agp_bind_hat_axis(AndroidGamepadAdapter *adapter,
                       int32_t android_axis_code,
                       uint16_t negative_mask,
                       uint16_t positive_mask);

/* Returns true only when an event code is configured and accepted. */
bool agp_on_key(AndroidGamepadAdapter *adapter,
                int32_t android_key_code,
                bool down);
bool agp_on_axis(AndroidGamepadAdapter *adapter,
                 int32_t android_axis_code,
                 float normalized_value);
void agp_read_sample(const AndroidGamepadAdapter *adapter,
                     AndroidGamepadSample *sample);

/* Convert Android [-1, 1] axis values using neutral=0 and game range [-128,127]. */
int16_t agp_normalize_axis(float normalized_value);

#ifdef __cplusplus
}
#endif

#endif
