# Build and Release Record

## Current state

- No Android app sources, Gradle wrapper, CMake project for the game, APK/AAB, or release build is available.
- This baseline directory itself is not an Android application and cannot be installed or played.
- Host CMake, Java and Clang exist, but no Android SDK/NDK/Gradle/ADB was found in the inspected environment.
- No emulator or physical Android device has been demonstrated as available.

## Current inspection-tool build

`tools/archive_inventory.c` and `tools/extract_1945.c` were compiled as host utilities using `cc -Wall -Wextra -Werror ... -larchive`. These tools only read/list/extract the supplied archive; they are not part of the game runtime and were not built for Android.

Example inventory build:

```sh
cc -Wall -Wextra -Werror tools/archive_inventory.c -larchive -o /tmp/archive_inventory
/tmp/archive_inventory "/path/to/1945 I & II (Europe) (En,Fr,De,Es,It).7z"
```

## Release eligibility

**Not eligible for release.** No native gameplay, application package, runtime validation, fidelity comparison, lifecycle tests, performance data, or release artifact exists. Do not label the archive or this checkpoint as a port.

## Required before the next Android build attempt

1. Confirm whether the actual existing project repository must be provided or cloned into this workspace.
2. Establish and record exact Android SDK, NDK, CMake, AGP, Gradle, and Java versions.
3. Complete read-only raw-disc, filesystem, ELF and asset inventory tasks.
4. Preserve logs and failing tests; do not loosen tests without evidence.
