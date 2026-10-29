"""Static/compile checks connecting the prototype simulation, renderer, JNI, and Android shell."""
from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]
CPP_DIR = ROOT / "app/src/main/cpp"
GAME_DIR = CPP_DIR / "game"
JAVA_STUBS = ROOT / "tests/java_stubs/src"
ANDROID_NS = "{http://schemas.android.com/apk/res/android}"


def _java_home() -> pathlib.Path:
    javac = shutil.which("javac")
    if javac is None:
        raise RuntimeError("javac is required for native bridge syntax validation")
    resolved = pathlib.Path(javac).resolve()
    return resolved.parent.parent


def test_renderer_and_jni_bridge_strict_cpp_syntax() -> None:
    clang = shutil.which("clang++") or shutil.which("g++")
    assert clang is not None, "a C++17 compiler is required"
    common = [clang, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-Wconversion",
              "-Wsign-conversion", "-pedantic", "-fsyntax-only"]
    renderer = subprocess.run(
        common + ["-I", str(ROOT / "tests/native_stubs"), "-I", str(GAME_DIR),
                  str(GAME_DIR / "game_renderer.cpp")],
        capture_output=True, text=True,
    )
    assert renderer.returncode == 0, renderer.stdout + renderer.stderr

    java_home = _java_home()
    bridge = subprocess.run(
        common + ["-I", str(java_home / "include"), "-I", str(java_home / "include/linux"),
                  "-I", str(GAME_DIR), "-I", str(ROOT / "tools/reference_model"),
                  str(GAME_DIR / "game_bridge.cpp")],
        capture_output=True, text=True,
    )
    assert bridge.returncode == 0, bridge.stdout + bridge.stderr

    c_compiler = shutil.which("gcc") or shutil.which("clang")
    assert c_compiler is not None, "a C11 compiler is required for input JNI syntax validation"
    input_bridge = subprocess.run(
        [c_compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wconversion",
         "-Wsign-conversion", "-pedantic", "-fsyntax-only", "-I", str(java_home / "include"),
         "-I", str(java_home / "include/linux"), "-I", str(ROOT / "tools/reference_model"),
         str(CPP_DIR / "input_bridge.c")],
        capture_output=True, text=True,
    )
    assert input_bridge.returncode == 0, input_bridge.stdout + input_bridge.stderr


def test_all_android_java_sources_compile_against_platform_contract_stubs(tmp_path: pathlib.Path) -> None:
    javac = shutil.which("javac")
    assert javac is not None, "javac is required for Java syntax validation"
    output = tmp_path / "classes"
    output.mkdir()
    sources = sorted(JAVA_STUBS.rglob("*.java")) + sorted((ROOT / "app/src/main/java").rglob("*.java"))
    result = subprocess.run(
        [javac, "-Xlint:all", "-Werror", "-d", str(output)] + [str(p) for p in sources],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_manifest_launches_game_and_keeps_diagnostic_activity_internal() -> None:
    manifest = ET.parse(ROOT / "app/src/main/AndroidManifest.xml").getroot()
    application = manifest.find("application")
    assert application is not None
    activities = {item.get(ANDROID_NS + "name"): item for item in application.findall("activity")}
    game = activities[".game.GameActivity"]
    gles_feature = manifest.find("uses-feature")
    assert gles_feature is not None
    assert gles_feature.get(ANDROID_NS + "glEsVersion") == "0x00020000"
    assert gles_feature.get(ANDROID_NS + "required") == "true"
    assert game.get(ANDROID_NS + "exported") == "true"
    assert game.get(ANDROID_NS + "screenOrientation") == "landscape"
    filters = game.findall("intent-filter")
    assert len(filters) == 1
    actions = {a.get(ANDROID_NS + "name") for a in filters[0].findall("action")}
    categories = {c.get(ANDROID_NS + "name") for c in filters[0].findall("category")}
    assert "android.intent.action.MAIN" in actions
    assert "android.intent.category.LAUNCHER" in categories
    assert activities[".MainActivity"].get(ANDROID_NS + "exported") == "false"


def test_cmake_includes_native_game_audio_renderer_and_existing_input_core() -> None:
    cmake = (CPP_DIR / "CMakeLists.txt").read_text(encoding="utf-8")
    required = [
        "input_bridge.c", "android_gamepad_adapter.c", "ps2_pad_report.c",
        "game_core.c", "audio_engine.c", "game_renderer.cpp", "game_bridge.cpp",
        "GLESv2", "m",
    ]
    for entry in required:
        assert entry in cmake, f"CMakeLists.txt is missing required native component/link: {entry}"
    for rel in [
        "app/src/main/cpp/game/game_core.h",
        "app/src/main/cpp/game/audio_engine.h",
        "app/src/main/cpp/game/game_renderer.h",
        "app/src/main/java/org/mkvium/port1945/game/GameActivity.java",
        "app/src/main/java/org/mkvium/port1945/game/GameSurfaceView.java",
        "app/src/main/java/org/mkvium/port1945/game/GameAudio.java",
        "app/src/main/java/org/mkvium/port1945/game/GameBridge.java",
    ]:
        assert (ROOT / rel).is_file(), f"missing project integration file: {rel}"


def test_jni_declarations_have_matching_implementations() -> None:
    java = (ROOT / "app/src/main/java/org/mkvium/port1945/game/GameBridge.java").read_text(encoding="utf-8")
    cpp = (GAME_DIR / "game_bridge.cpp").read_text(encoding="utf-8")
    methods = re.findall(r"native\s+\w+(?:\[\])?\s+(native\w+)\s*\(", java)
    assert methods
    for method in methods:
        assert f"Java_org_mkvium_port1945_game_GameBridge_{method}" in cpp, f"JNI implementation missing {method}"


def test_gameplay_is_explicitly_documented_as_prototype_not_original_parity() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8").lower()
    milestone = (ROOT / "MILESTONE_01_PROTOTYPE.md").read_text(encoding="utf-8").lower()
    assert "not yet a faithful" in readme or "not a faithful" in readme
    assert "procedural" in readme and "original" in readme
    assert "prototype" in milestone and "not" in milestone


def test_android_pause_edges_ignore_key_repeat_and_audio_writes_handle_partial_progress() -> None:
    surface = (ROOT / "app/src/main/java/org/mkvium/port1945/game/GameSurfaceView.java").read_text(encoding="utf-8")
    audio = (ROOT / "app/src/main/java/org/mkvium/port1945/game/GameAudio.java").read_text(encoding="utf-8")
    assert surface.count("event.getRepeatCount() == 0") >= 2
    assert "top right to pause" in surface
    assert "public synchronized void stop()" in audio
    assert "while (running && offset < samples.length)" in audio
    assert "if (written <= 0)" in audio
    assert audio.count('Log.w("1945Audio", "AudioTrack') >= 4
    bridge = (GAME_DIR / "game_bridge.cpp").read_text(encoding="utf-8")
    lifecycle = bridge[bridge.index("Java_org_mkvium_port1945_game_GameBridge_nativePauseForLifecycle"):]
    lifecycle = lifecycle[:lifecycle.index("Java_org_mkvium_port1945_game_GameBridge_nativeInitAudio")]
    assert "g_pending_audio_events.store(0u, std::memory_order_release)" in lifecycle


def test_renderer_reinitializes_names_for_a_new_egl_context_without_deleting_stale_ids() -> None:
    renderer = (GAME_DIR / "game_renderer.cpp").read_text(encoding="utf-8")
    body_start = renderer.index('extern "C" void game_renderer_surface_created(void)')
    body_end = renderer.index('extern "C" void game_renderer_surface_changed', body_start)
    surface_created = renderer[body_start:body_end]
    assert "new EGL context may have replaced the old one" in surface_created
    assert "g_vertex_buffer = 0u;" in surface_created
    assert "g_program = 0u;" in surface_created
    reset_prefix = surface_created[:surface_created.index("const GLuint vertex_shader")]
    assert "glDeleteBuffers" not in reset_prefix
    assert "glDeleteProgram" not in reset_prefix
    # Object cleanup remains required for a program that failed linking in this live context.
    assert "glDeleteProgram(g_program);" in surface_created


def test_original_game_media_and_binary_databases_are_not_in_the_source_tree() -> None:
    excluded_suffixes = {".7z", ".bin", ".cue", ".iso", ".elf", ".gzf", ".pss", ".tim", ".vag", ".adx", ".apk", ".aab"}
    ignored_dirs = {".git", ".pytest_cache", "__pycache__", "build", ".gradle", ".cxx", "source-media-working-copy"}
    for path in ROOT.rglob("*"):
        if any(part in ignored_dirs for part in path.parts):
            continue
        if path.is_file():
            assert path.suffix.lower() not in excluded_suffixes, f"excluded binary/media in source tree: {path.relative_to(ROOT)}"
            assert path.stat().st_size < 15 * 1024 * 1024, f"unexpected large file in source tree: {path.relative_to(ROOT)}"


def test_native_cmake_project_configures_on_host(tmp_path: pathlib.Path) -> None:
    cmake = shutil.which("cmake")
    assert cmake is not None, "CMake is required for native project configure validation"
    result = subprocess.run(
        [cmake, "-S", str(CPP_DIR), "-B", str(tmp_path / "cmake-configure"), "-Wno-dev"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    generated = tmp_path / "cmake-configure" / "Makefile"
    assert generated.is_file(), "CMake did not generate the expected host Makefile"
