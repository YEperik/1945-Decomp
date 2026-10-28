#include "android_gamepad_adapter.h"

#include <limits.h>

static float clamp_normalized(float value)
{
    if (!(value == value)) { /* NaN -> neutral; infinities are clamped below. */
        return 0.0f;
    }
    if (value < -1.0f) {
        return -1.0f;
    }
    if (value > 1.0f) {
        return 1.0f;
    }
    return value;
}

int16_t agp_normalize_axis(float normalized_value)
{
    float scaled;
    int32_t rounded;

    normalized_value = clamp_normalized(normalized_value);
    /* Use 128 on the negative side and 127 on the positive side, preserving
       the signed values represented by an unsigned byte minus 0x80. */
    scaled = normalized_value < 0.0f
                 ? normalized_value * 128.0f
                 : normalized_value * 127.0f;
    rounded = scaled < 0.0f ? (int32_t)(scaled - 0.5f)
                            : (int32_t)(scaled + 0.5f);
    if (rounded < -128) {
        rounded = -128;
    } else if (rounded > 127) {
        rounded = 127;
    }
    return (int16_t)rounded;
}

void agp_init(AndroidGamepadAdapter *adapter)
{
    size_t i;
    if (adapter == NULL) {
        return;
    }
    *adapter = (AndroidGamepadAdapter){0};
    for (i = 0; i < AGP_AXIS_COUNT; ++i) {
        adapter->axis_code[i] = INT32_MIN;
    }
    adapter->connected = false;
}

void agp_set_connected(AndroidGamepadAdapter *adapter, bool connected)
{
    size_t i;
    if (adapter == NULL) {
        return;
    }
    adapter->connected = connected;
    if (!connected) {
        for (i = 0; i < adapter->key_count; ++i) {
            adapter->keys[i].down = false;
        }
        for (i = 0; i < AGP_AXIS_COUNT; ++i) {
            adapter->axis_value[i] = 0.0f;
        }
        for (i = 0; i < adapter->hat_count; ++i) {
            adapter->hats[i].value = 0.0f;
        }
    }
}

bool agp_bind_key(AndroidGamepadAdapter *adapter,
                  int32_t android_key_code,
                  uint16_t output_mask)
{
    size_t i;
    if (adapter == NULL || output_mask == 0) {
        return false;
    }
    for (i = 0; i < adapter->key_count; ++i) {
        if (adapter->keys[i].android_key_code == android_key_code) {
            adapter->keys[i].output_mask = output_mask;
            adapter->keys[i].down = false;
            return true;
        }
    }
    if (adapter->key_count >= AGP_MAX_KEY_BINDINGS) {
        return false;
    }
    adapter->keys[adapter->key_count++] = (AgpKeyBinding){
        .android_key_code = android_key_code,
        .output_mask = output_mask,
        .down = false,
    };
    return true;
}

bool agp_bind_axis(AndroidGamepadAdapter *adapter,
                   int32_t android_axis_code,
                   AgpAxisTarget target)
{
    if (adapter == NULL || target < AGP_AXIS_A_X || target > AGP_AXIS_B_Y) {
        return false;
    }
    adapter->axis_code[(size_t)target] = android_axis_code;
    adapter->axis_bound[(size_t)target] = true;
    adapter->axis_value[(size_t)target] = 0.0f;
    return true;
}

bool agp_bind_hat_axis(AndroidGamepadAdapter *adapter,
                       int32_t android_axis_code,
                       uint16_t negative_mask,
                       uint16_t positive_mask)
{
    size_t i;
    if (adapter == NULL || (negative_mask == 0 && positive_mask == 0)) {
        return false;
    }
    for (i = 0; i < adapter->hat_count; ++i) {
        if (adapter->hats[i].android_axis_code == android_axis_code) {
            adapter->hats[i].negative_mask = negative_mask;
            adapter->hats[i].positive_mask = positive_mask;
            adapter->hats[i].value = 0.0f;
            return true;
        }
    }
    if (adapter->hat_count >= AGP_MAX_HAT_BINDINGS) {
        return false;
    }
    adapter->hats[adapter->hat_count++] = (AgpHatBinding){
        .android_axis_code = android_axis_code,
        .negative_mask = negative_mask,
        .positive_mask = positive_mask,
        .value = 0.0f,
        .configured = true,
    };
    return true;
}

bool agp_on_key(AndroidGamepadAdapter *adapter,
                int32_t android_key_code,
                bool down)
{
    size_t i;
    if (adapter == NULL || !adapter->connected) {
        return false;
    }
    for (i = 0; i < adapter->key_count; ++i) {
        if (adapter->keys[i].android_key_code == android_key_code) {
            adapter->keys[i].down = down;
            return true;
        }
    }
    return false;
}

bool agp_on_axis(AndroidGamepadAdapter *adapter,
                 int32_t android_axis_code,
                 float normalized_value)
{
    size_t i;
    bool matched = false;
    if (adapter == NULL || !adapter->connected) {
        return false;
    }
    normalized_value = clamp_normalized(normalized_value);
    for (i = 0; i < AGP_AXIS_COUNT; ++i) {
        if (adapter->axis_bound[i] && adapter->axis_code[i] == android_axis_code) {
            adapter->axis_value[i] = normalized_value;
            matched = true;
        }
    }
    for (i = 0; i < adapter->hat_count; ++i) {
        if (adapter->hats[i].configured &&
            adapter->hats[i].android_axis_code == android_axis_code) {
            adapter->hats[i].value = normalized_value;
            matched = true;
        }
    }
    return matched;
}

void agp_read_sample(const AndroidGamepadAdapter *adapter,
                     AndroidGamepadSample *sample)
{
    size_t i;
    if (sample == NULL) {
        return;
    }
    *sample = (AndroidGamepadSample){0};
    if (adapter == NULL || !adapter->connected) {
        sample->connected = false;
        return;
    }
    sample->connected = true;
    for (i = 0; i < adapter->key_count; ++i) {
        if (adapter->keys[i].down) {
            sample->buttons_mask = (uint16_t)(sample->buttons_mask |
                                                adapter->keys[i].output_mask);
        }
    }
    for (i = 0; i < adapter->hat_count; ++i) {
        const AgpHatBinding *hat = &adapter->hats[i];
        const int16_t value = agp_normalize_axis(hat->value);
        if (!hat->configured) {
            continue;
        }
        if (value < -63) {
            sample->buttons_mask = (uint16_t)(sample->buttons_mask |
                                                hat->negative_mask);
        } else if (value >= 64) {
            sample->buttons_mask = (uint16_t)(sample->buttons_mask |
                                                hat->positive_mask);
        }
    }
    for (i = 0; i < AGP_AXIS_COUNT; ++i) {
        if (adapter->axis_bound[i]) {
            sample->axes[i] = agp_normalize_axis(adapter->axis_value[i]);
        }
    }
}
