plugins {
    id("com.android.application")
}

android {
    namespace = "org.YEperik-1945-Decomp.port1945"
    compileSdk = 36

    defaultConfig {
        applicationId = "org.YEperik.port1945"
        minSdk = 23
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0-ci"

        ndk {
            abiFilters += setOf("arm64-v8a", "armeabi-v7a", "x86_64")
        }

        externalNativeBuild {
            cmake {
                arguments += listOf("-DANDROID_PLATFORM=android-23")
            }
        }
    }

    externalNativeBuild {
        cmake {
            path = file("src/main/cpp/CMakeLists.txt")
            version = "3.31.6"
        }
    }

    buildTypes {
        debug {
            applicationIdSuffix = ".debug"
            versionNameSuffix = "-debug"
        }
        release {
            isMinifyEnabled = false
        }
    }
}
