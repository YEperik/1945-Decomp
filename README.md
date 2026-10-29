# 1945 Native Android Port — Evidence-led research + explicit prototype

This repository now has two clearly separated parts: (1) reverse-engineering evidence collected from the supplied PAL PS2 image/listings, and (2) an **authored native gameplay/renderer/procedural-SFX prototype** used to exercise the Android runtime architecture. The prototype is **not yet a faithful port** and is not presented as original `1945 I & II` gameplay, art, or sound.

## Current milestone: native vertical slice prototype

The Android launcher is `org.mkvium.port1945.game.GameActivity`, hosted by `GameSurfaceView` on OpenGL ES 2.0. The input probe remains available via the `INPUT` button.

- `app/src/main/cpp/game/game_core.c`: deterministic fixed-step 60 Hz sample simulation, movement bounds, player shots, seeded enemy spawn/movement, aimed enemy projectiles, collisions, score/lives/invulnerability, READY/PLAYING/PAUSED/GAME_OVER, pause/restart and bounded update catch-up.
- `app/src/main/cpp/game/game_renderer.cpp`: procedural GLES2 geometry, stars, simple ships/projectiles/HUD/font, with 320×240 logical coordinates and a centered 4:3 viewport. It does not load game TIM textures or original stages.
- `app/src/main/cpp/game/audio_engine.c`: bounded mono PCM16 SFX mixer at 22,050 Hz for start, fire, enemy down, player hit, pause and game over. `GameAudio.java` streams it through `AudioTrack` on a dedicated worker. No original BGM, PSS decoder or original SFX-bank decoder is present.
- `app/src/main/cpp/game/game_bridge.cpp`: narrow JNI interface, game simulation and GLES render called on GL thread, an atomic event mask between gameplay and the dedicated audio thread.
- `GameSurfaceView.java`: touch stick/fire/pause plus keyboard and one active gamepad. These are convenience prototype controls, not verified PS2 button mappings.
- `app/src/main/cpp/game/tim_image.c` and `tools/tim_assets.py`: bounded native/Python TIM decoding; all 297 extracted TIMs cross-validate byte-for-byte. This does not yet map textures into gameplay.
- `app/src/main/cpp/game/tim_texture_renderer.cpp`: bounded GLES texture cache and textured-quad primitive, mock-tested but not yet wired into the gameplay renderer.
- `.github/workflows/android-ci.yml`: push on all branches, manifest/repository hygiene checks, host regression tests, Android lint, debug APK assembly, and a 14-day artifact upload when run on GitHub Actions.

The exact boundary and next gates are in [`MILESTONE_01_PROTOTYPE.md`](MILESTONE_01_PROTOTYPE.md).

## What is still missing for a genuine port

- **Original renderer/assets:** the bounded TIM decoder exists and matches the Python reference for 297/297 local files, but decoded textures are not wired into the renderer. Sprite atlas/source rectangles, CLUT selection, original fonts, stage maps, animation tables, effects and scene composition remain unresolved.
- **Original audio:** no original BGM, PSS demultiplexer/decoder, original sound-bank parser, or fidelity comparison. Current procedural tones are only runtime test SFX.
- **Original gameplay:** stage scripts, exact enemy/projectile patterns, player/weapons, bosses, menu/progression, scoring/difficulty rules and game timing remain to be reconstructed from evidence or reference observations. The current simulation rules are invented prototype rules.
- **Android proof:** this environment has no Android SDK/NDK, Gradle, emulator or ADB. The GitHub connector is authenticated as `MKvium`, not the requested `YEperik` owner, so no remote push or hosted run was attempted. The official Android Gradle/NDK build, lint result, APK install/launch, GLES driver behavior, AudioTrack playback/underruns, device input and frame performance are all still **NOT RUN** until the workflow executes on a GitHub runner and the APK is tested on Android.
- **Reverse-engineering toolchain:** the Ghidra R5900-aware runner is prepared, but Ghidra and the Emotion Engine extension have not been run in this environment.

## Reverse-engineering baseline retained

- `SYSTEM.CNF;1` refers to `SLES_517.41;1` and `VMODE = PAL`. These are metadata observations, not provenance/authenticity proof.
- `tools/disc_inventory.py`, `tools/cdrom_integrity.c`, `tools/elf_recon.py`, and `tools/static_control_flow.py` record bounded inventory and static reconnaissance. Opcode-pattern counts are candidates, not verified function counts or execution traces.
- The saved controller listings and `tools/reference_model/ps2_pad_report.{h,c}` capture selected numeric input-state semantics. Named physical-button mappings, controller status-code semantics, and several API contracts remain unresolved.
- Original archive, raw disc image, extracted proprietary media and complete Ghidra database/decompiler export must remain outside source control. This repository does not bundle those materials. `tools/verify_disc_manifest.py` performs a complete path/size/hash audit against an external extraction; `tools/check_repository_hygiene.py` checks the tracked tree before upload.

## Build and test

Host tests need Python 3.13+, `pytest`, `PyYAML`, GCC/Clang, C++17 compiler, CMake, and JDK 17+. Run:

```sh
python -m pip install pytest pyyaml
pytest -q
```

Tests compile and run the C prototype simulation/audio mixer, exercise fixed-step/state/collision/audio invariants, compile C++ renderer/JNI interfaces against small local API-contract stubs, compile Java source against minimal platform stubs, and validate manifest/Gradle/CMake/workflow wiring. These stubs do not replace the official Android SDK/NDK build or device tests.

The official hosted build is configured in `.github/workflows/android-ci.yml`; it validates manifest metadata and repository hygiene, runs host tests, then runs `:app:lintDebug`, `:app:assembleDebug`, and uploads `app-debug.apk` as `1945-native-port-debug-apk` if all gates pass. Current local `pytest -q` is **86 passed**. No hosted workflow run or APK artifact is claimed yet. A native PC/desktop runtime is not implemented. See [`GITHUB_ACTIONS_SETUP.md`](GITHUB_ACTIONS_SETUP.md).

## Key records

- [`PROJECT_STATUS.md`](PROJECT_STATUS.md): accumulated engineering status and verification history.
- [`ARCHITECTURE.md`](ARCHITECTURE.md): module boundaries and implementation status.
- [`KNOWN_ISSUES.md`](KNOWN_ISSUES.md): blockers and unresolved risks.
- [`TEST_MATRIX.md`](TEST_MATRIX.md): test evidence and execution boundaries.
- [`evidence/disc_inventory.json`](evidence/disc_inventory.json) and [`evidence/disc_file_manifest.csv`](evidence/disc_file_manifest.csv): image inventory/check results.
- [`evidence/static_control_flow_report.md`](evidence/static_control_flow_report.md): conservative static-control-transfer index.
- [`evidence/controller_input_disassembly_reconstruction.md`](evidence/controller_input_disassembly_reconstruction.md): controller input-state reconstruction from submitted listings.
- [`evidence/prototype_host_validation.txt`](evidence/prototype_host_validation.txt): latest local build/test checks for this milestone, when generated.

## Runtime policy

The shipped application must not execute the original PS2 ELF, embed a PS2 emulator/VM as the game engine, or present generated prototype assets/audio as original content. Replace prototype code incrementally only when the corresponding original behavior or file format is supported by evidence and repeatable regression tests.
