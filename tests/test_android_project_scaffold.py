from pathlib import Path
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
JAVA_PACKAGE = "org.mkvium.port1945"
JNI_PREFIX = "Java_org_mkvium_port1945_NativeInputBridge_"


def test_manifest_declares_existing_launcher_activity():
    manifest = ET.parse(ROOT / "app/src/main/AndroidManifest.xml").getroot()
    android_ns = "{http://schemas.android.com/apk/res/android}"
    app = manifest.find("application")
    assert app is not None
    activity = app.find("activity")
    assert activity is not None
    assert activity.attrib[android_ns + "name"] == ".MainActivity"
    assert activity.attrib[android_ns + "exported"] == "true"
    class_path = ROOT / "app/src/main/java" / Path(*JAVA_PACKAGE.split(".")) / "MainActivity.java"
    assert class_path.is_file()
    source = class_path.read_text(encoding="utf-8")
    assert f"package {JAVA_PACKAGE};" in source
    assert "implements InputManager.InputDeviceListener" in source
    assert "import android.text.InputType;" in source


def test_every_native_java_declaration_has_matching_jni_export():
    java_path = ROOT / "app/src/main/java" / Path(*JAVA_PACKAGE.split(".")) / "NativeInputBridge.java"
    java_source = java_path.read_text(encoding="utf-8")
    c_source = (ROOT / "app/src/main/cpp/input_bridge.c").read_text(encoding="utf-8")
    declared = set(re.findall(r"public static native\s+[\w\[\]]+\s+(native\w+)\s*\(", java_source))
    exported = set(re.findall(r"Java_org_mkvium_port1945_NativeInputBridge_(native\w+)\s*\(", c_source))
    assert declared, "JNI bridge declarations were not found"
    assert declared == exported, f"JNI declaration/export mismatch: Java={declared}, C={exported}"


def test_manual_bindings_are_persistent_and_no_default_mapping_is_assumed():
    activity = (ROOT / "app/src/main/java" / Path(*JAVA_PACKAGE.split(".")) / "MainActivity.java").read_text(encoding="utf-8")
    assert 'getSharedPreferences("numeric_input_bindings"' in activity
    assert "NativeInputBridge.nativeBindKey(keyCode, mask)" in activity
    assert "NativeInputBridge.nativeBindAxis(axisCode, target)" in activity
    assert "NativeInputBridge.nativeBindHatAxis(axisCode, negativeMask, positiveMask)" in activity
    assert "NativeInputBridge.nativeResetBindings();" in activity
    assert "SharedPreferences preferences = getSharedPreferences" in activity
    assert "No default button mapping" in activity or "no default mapping" in activity.lower()
    assert "device.getId() == activeControllerId" in activity
    assert "NativeInputBridge.nativeTick();" in activity


def test_gradle_native_and_workflow_paths_are_complete():
    app_gradle = (ROOT / "app/build.gradle.kts").read_text(encoding="utf-8")
    root_gradle = (ROOT / "build.gradle.kts").read_text(encoding="utf-8")
    cmake = (ROOT / "app/src/main/cpp/CMakeLists.txt").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/android-ci.yml").read_text(encoding="utf-8")
    assert 'id("com.android.application")' in app_gradle
    assert 'version "8.13.2"' in root_gradle
    assert 'version = "3.31.6"' in app_gradle
    assert '"${REFERENCE_MODEL_DIR}/android_gamepad_adapter.c"' in cmake
    assert '"${REFERENCE_MODEL_DIR}/ps2_pad_report.c"' in cmake
    assert "gradle-version: '8.13'" in workflow
    assert ":app:lintDebug" in workflow
    assert ":app:assembleDebug" in workflow
    assert "actions/upload-artifact@v7" in workflow
    assert "retention-days: 14" in workflow
    assert "pytest -q" in workflow
    assert "source-media-working-copy" not in workflow


def test_game_media_and_exported_binary_assets_are_not_tracked():
    import subprocess

    if (ROOT / ".git").exists():
        tracked = subprocess.run(
            ["git", "ls-files"], cwd=ROOT, check=True, text=True, capture_output=True
        ).stdout.splitlines()
    else:
        # Let the source-only ZIP run its tests too, even without Git metadata.
        tracked = [path.relative_to(ROOT).as_posix()
                   for path in ROOT.rglob("*") if path.is_file()]
    excluded_suffixes = (".7z", ".bin", ".cue", ".iso", ".elf", ".gzf")
    offending = [path for path in tracked if path.lower().endswith(excluded_suffixes)]
    assert not offending, f"Potential proprietary media/binaries tracked: {offending}"


def test_diagnostic_form_and_log_remain_scrollable_on_short_screens():
    activity = (ROOT / "app/src/main/java" / Path(*JAVA_PACKAGE.split(".")) / "MainActivity.java").read_text(encoding="utf-8")
    assert "ScrollView pageScroll = new ScrollView(this);" in activity
    assert "pageScroll.setFillViewport(true);" in activity
    assert "LinearLayout.LayoutParams.MATCH_PARENT, dp(180)" in activity
    assert 'clearBindingsButton.setText("Clear all bindings")' in activity
