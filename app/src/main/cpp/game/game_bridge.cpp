#include <jni.h>

#include "audio_engine.h"
#include "game_core.h"
#include "game_renderer.h"

#include <atomic>
#include <cstdint>

namespace {
GameWorld g_world{};
AudioEngine g_audio{};
std::atomic<std::uint32_t> g_pending_audio_events{0u};
bool g_game_initialized = false;

void ensure_game_initialized()
{
    if (!g_game_initialized) {
        game_world_init(&g_world, 0x1945a11u);
        g_game_initialized = true;
    }
}
} // namespace

extern "C" JNIEXPORT void JNICALL
Java_org_mkvium_port1945_game_GameBridge_nativeInitGame(JNIEnv *, jclass)
{
    game_world_init(&g_world, 0x1945a11u);
    g_pending_audio_events.store(0u, std::memory_order_relaxed);
    g_game_initialized = true;
}

extern "C" JNIEXPORT void JNICALL
Java_org_mkvium_port1945_game_GameBridge_nativeSurfaceCreated(JNIEnv *, jclass)
{
    ensure_game_initialized();
    game_renderer_surface_created();
}

extern "C" JNIEXPORT void JNICALL
Java_org_mkvium_port1945_game_GameBridge_nativeSurfaceChanged(JNIEnv *, jclass,
                                                               jint width, jint height)
{
    game_renderer_surface_changed(static_cast<int>(width), static_cast<int>(height));
}

extern "C" JNIEXPORT void JNICALL
Java_org_mkvium_port1945_game_GameBridge_nativeFrame(JNIEnv *, jclass,
                                                      jfloat delta_seconds,
                                                      jfloat move_x,
                                                      jfloat move_y,
                                                      jboolean fire_down,
                                                      jboolean pause_pressed)
{
    ensure_game_initialized();
    GameInput input{};
    input.move_x = static_cast<float>(move_x);
    input.move_y = static_cast<float>(move_y);
    input.fire_down = fire_down == JNI_TRUE ? 1u : 0u;
    input.pause_pressed = pause_pressed == JNI_TRUE ? 1u : 0u;
    const std::uint32_t events = game_world_update(&g_world,
                                                    static_cast<float>(delta_seconds), input);
    if (events != 0u) {
        g_pending_audio_events.fetch_or(events, std::memory_order_relaxed);
    }
    game_renderer_draw(&g_world);
}

extern "C" JNIEXPORT void JNICALL
Java_org_mkvium_port1945_game_GameBridge_nativePauseForLifecycle(JNIEnv *, jclass)
{
    ensure_game_initialized();
    game_world_force_pause(&g_world);
    /* The GL thread has already been paused by GLSurfaceView; discard stale SFX
       events so a sound queued just before backgrounding is not replayed on resume. */
    g_pending_audio_events.store(0u, std::memory_order_release);
}

extern "C" JNIEXPORT void JNICALL
Java_org_mkvium_port1945_game_GameBridge_nativeInitAudio(JNIEnv *, jclass)
{
    audio_engine_init(&g_audio);
}

extern "C" JNIEXPORT void JNICALL
Java_org_mkvium_port1945_game_GameBridge_nativeMixAudio(JNIEnv *env, jclass,
                                                         jshortArray output)
{
    if (output == nullptr) {
        return;
    }
    const jsize length = env->GetArrayLength(output);
    if (length <= 0) {
        return;
    }
    jshort *samples = env->GetShortArrayElements(output, nullptr);
    if (samples == nullptr) {
        return;
    }
    const std::uint32_t events = g_pending_audio_events.exchange(0u, std::memory_order_acq_rel);
    audio_engine_render(&g_audio, events,
                        reinterpret_cast<std::int16_t *>(samples), static_cast<std::size_t>(length));
    env->ReleaseShortArrayElements(output, samples, 0);
}
