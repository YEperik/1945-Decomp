#include <jni.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#include "android_gamepad_adapter.h"
#include "ps2_pad_report.h"

#define SNAPSHOT_SIZE 11

static AndroidGamepadAdapter g_adapter;
static Ps2PadRecord g_record;
static bool g_initialized = false;

static void ensure_initialized(void)
{
    if (g_initialized) {
        return;
    }
    agp_init(&g_adapter);
    memset(&g_record, 0, sizeof(g_record));
    g_initialized = true;
}

static void apply_sample(void)
{
    AndroidGamepadSample sample;
    agp_read_sample(&g_adapter, &sample);
    (void)ps2_pad_apply_native_sample(&g_record,
                                     sample.buttons_mask,
                                     sample.axes,
                                     sample.connected);
}

JNIEXPORT jstring JNICALL
Java_org_mkvium_port1945_NativeInputBridge_nativeVersion(JNIEnv *env, jclass clazz)
{
    (void)clazz;
    ensure_initialized();
    return (*env)->NewStringUTF(env, "Portable C input core 0.1.0; no default button mapping");
}

JNIEXPORT void JNICALL
Java_org_mkvium_port1945_NativeInputBridge_nativeInit(JNIEnv *env, jclass clazz)
{
    (void)env;
    (void)clazz;
    agp_init(&g_adapter);
    memset(&g_record, 0, sizeof(g_record));
    g_initialized = true;
}

JNIEXPORT jboolean JNICALL
Java_org_mkvium_port1945_NativeInputBridge_nativeBindKey(JNIEnv *env, jclass clazz,
                                                          jint key_code, jint output_mask)
{
    (void)env;
    (void)clazz;
    ensure_initialized();
    if (output_mask <= 0 || output_mask > 0xffff) {
        return JNI_FALSE;
    }
    return agp_bind_key(&g_adapter, (int32_t)key_code, (uint16_t)output_mask)
               ? JNI_TRUE : JNI_FALSE;
}

JNIEXPORT jboolean JNICALL
Java_org_mkvium_port1945_NativeInputBridge_nativeBindAxis(JNIEnv *env, jclass clazz,
                                                           jint axis_code, jint target)
{
    (void)env;
    (void)clazz;
    ensure_initialized();
    if (target < (jint)AGP_AXIS_A_X || target > (jint)AGP_AXIS_B_Y) {
        return JNI_FALSE;
    }
    return agp_bind_axis(&g_adapter, (int32_t)axis_code, (AgpAxisTarget)target)
               ? JNI_TRUE : JNI_FALSE;
}

JNIEXPORT jboolean JNICALL
Java_org_mkvium_port1945_NativeInputBridge_nativeBindHatAxis(JNIEnv *env, jclass clazz,
                                                              jint axis_code,
                                                              jint negative_mask,
                                                              jint positive_mask)
{
    (void)env;
    (void)clazz;
    ensure_initialized();
    if (negative_mask < 0 || negative_mask > 0xffff ||
        positive_mask < 0 || positive_mask > 0xffff ||
        (negative_mask == 0 && positive_mask == 0)) {
        return JNI_FALSE;
    }
    return agp_bind_hat_axis(&g_adapter, (int32_t)axis_code,
                             (uint16_t)negative_mask, (uint16_t)positive_mask)
               ? JNI_TRUE : JNI_FALSE;
}

JNIEXPORT void JNICALL
Java_org_mkvium_port1945_NativeInputBridge_nativeSetConnected(JNIEnv *env, jclass clazz,
                                                               jboolean connected)
{
    (void)env;
    (void)clazz;
    ensure_initialized();
    agp_set_connected(&g_adapter, connected == JNI_TRUE);
    apply_sample();
}

JNIEXPORT jboolean JNICALL
Java_org_mkvium_port1945_NativeInputBridge_nativeOnKey(JNIEnv *env, jclass clazz,
                                                        jint key_code, jboolean down)
{
    bool accepted;
    (void)env;
    (void)clazz;
    ensure_initialized();
    accepted = agp_on_key(&g_adapter, (int32_t)key_code, down == JNI_TRUE);
    apply_sample();
    return accepted ? JNI_TRUE : JNI_FALSE;
}

JNIEXPORT jboolean JNICALL
Java_org_mkvium_port1945_NativeInputBridge_nativeOnAxis(JNIEnv *env, jclass clazz,
                                                         jint axis_code, jfloat value)
{
    bool accepted;
    (void)env;
    (void)clazz;
    ensure_initialized();
    accepted = agp_on_axis(&g_adapter, (int32_t)axis_code, (float)value);
    apply_sample();
    return accepted ? JNI_TRUE : JNI_FALSE;
}

JNIEXPORT jintArray JNICALL
Java_org_mkvium_port1945_NativeInputBridge_nativeSnapshot(JNIEnv *env, jclass clazz)
{
    jint values[SNAPSHOT_SIZE];
    jintArray array;
    (void)clazz;
    ensure_initialized();
    values[0] = g_adapter.connected ? 1 : 0;
    values[1] = (jint)g_record.current_pressed;
    values[2] = (jint)g_record.previous_pressed;
    values[3] = (jint)g_record.pressed_edges;
    values[4] = (jint)g_record.current_axis_directions;
    values[5] = (jint)g_record.previous_axis_directions;
    values[6] = (jint)g_record.axis_direction_edges;
    values[7] = (jint)g_record.axis_a_x;
    values[8] = (jint)g_record.axis_a_y;
    values[9] = (jint)g_record.axis_b_x;
    values[10] = (jint)g_record.axis_b_y;

    array = (*env)->NewIntArray(env, SNAPSHOT_SIZE);
    if (array != NULL) {
        (*env)->SetIntArrayRegion(env, array, 0, SNAPSHOT_SIZE, values);
    }
    return array;
}
