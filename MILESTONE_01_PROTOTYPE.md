# Milestone 01 — Native Gameplay/Renderer/Procedural-SFX Prototype

**Status:** source implementation and host checks present; official Android SDK/NDK build and device playback/rendering remain unverified.

## Scope delivered in this milestone

This milestone adds a clearly labelled prototype layer to the existing reverse-engineering/input diagnostic project. It is not represented as original `1945 I & II` gameplay or as a faithful port.

- `app/src/main/cpp/game/game_core.c`: deterministic fixed-step 60 Hz sample simulation with READY/PLAYING/PAUSED/GAME_OVER states, movement bounds, player shots, seeded enemy spawning/movement, aimed enemy projectiles, collision, score, lives, invulnerability, pause/restart, and bounded catch-up.
- `app/src/main/cpp/game/game_renderer.cpp`: OpenGL ES 2.0 renderer using a 320×240 logical viewport, centered 4:3 viewport, procedural background stars, generated ship/projectile geometry, HUD and small generated font. Shader compile/link failures, missing required shader locations, and VBO allocation failure are logged and fail closed; EGL context recreation resets stale resource names safely.
- `app/src/main/cpp/game/audio_engine.c`: bounded mono PCM16 22,050 Hz procedural SFX mixer. It produces prototype events; it does not decode the game’s original audio or contain BGM.
- `GameAudio.java`: Java `AudioTrack` blocking-write worker that owns and tears down the track. The native mixer is initialized and used on that worker, while gameplay-to-audio requests cross threads through an atomic event bitmask.
- `GameActivity.java` / `GameSurfaceView.java`: landscape immersive prototype host with touch movement/fire/pause, keyboard and one active gamepad. These convenient controls are not asserted to match the PS2 game's control mapping. Repeated key events cannot repeatedly toggle pause, and lifecycle pause clears a deferred pause edge. `MainActivity` remains available as an input event diagnostic screen.
- `game_bridge.cpp`: narrow JNI interface; game simulation and GLES calls run on the GL thread, audio sample mixing runs on its dedicated audio worker.
- `.github/workflows/android-ci.yml`: host tests and syntax checks, Android lint, debug APK build, and an artifact upload step for a GitHub-hosted runner.

## Boundaries and non-goals

No original TIM texture decoder, sprite atlas, stage background, original font, PSS decoder, original sound-bank reader, BGM, stage timeline, boss behavior, weapon system, title/menu progression, or original PS2 collision/timing semantics are implemented here. Current gameplay rules, velocities, geometry, font and SFX are authored prototype behavior.

The original PS2 ELF is not executed. A PS2 emulator/VM is not bundled. Proprietary source media and extracted proprietary assets are excluded from source control by policy and `.gitignore`.

## Verification plan

Run `pytest -q`. The tests compile/run the C simulation and audio core, check NaN/Inf axis handling, exercise pause/restart/collision/state limits, run address/undefined-behavior sanitizers where supported, compile renderer/JNI C++ against local API-contract stubs, compile Java against minimal Android API stubs, check manifest/Gradle/CMake/JNI wiring, and parse the Actions workflow.

The latest validation suite passes 66 tests, including C simulation/audio sanitizers, mock-GLES runtime checks, CMake configure, and Java/native syntax checks against stubs. Those host stubs check syntax and selected contracts only. They do not substitute for `:app:lintDebug`, `:app:assembleDebug`, installing an APK, exercising a real GLES driver, or hearing `AudioTrack` output. The GitHub-hosted Android build must pass before the APK can be called build-verified.

## Next milestone order

1. Obtain a real Android CI APK and fix any AGP/NDK/lint errors without weakening tests.
2. Install and exercise startup/lifecycle, touch and physical controller on an Android emulator/device; inspect audio underruns and renderer logs.
3. Reverse-engineer and document real TIM and PSS/audio data structures from authorized assets, including malformed-input tests and golden outputs.
4. Integrate original assets only after format evidence and validation; keep original gameplay behavior separate from prototype simulation until stage/game rules are supported by R5900 evidence or reference observation.
5. Replace prototype systems incrementally only when there are repeatable behavior comparisons; mark all unknown behavior and mismatches explicitly.
