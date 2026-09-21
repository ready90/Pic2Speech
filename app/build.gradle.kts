import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.chaquo.python")
}

android {
    namespace = "com.pic2speech.app"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.pic2speech.app"
        minSdk = 24                 // Chaquopy 硬性要求 >= 24
        targetSdk = 34
        versionCode = 1
        versionName = "1.0"

        // Python 解释器是原生组件，需指定 ABI。
        // arm64-v8a = 真机；x86_64 = 模拟器。只留 64 位可显著减小体积。
        ndk {
            abiFilters += listOf("arm64-v8a", "x86_64")
        }
    }

    buildTypes {
        getByName("release") {
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    // 注意：这里不能用 android { kotlinOptions { jvmTarget = "17" } }。
    // Kotlin 2.2.0 起 kotlinOptions{} 的弃用等级已提升为 error，编译直接失败。
    // jvmTarget 改为在下面的顶层 kotlin { compilerOptions { } } 里设置。
}

// Kotlin 2.x 的新写法（必须放在顶层，不能放进 android {} 块里）。
// 必须与上面 compileOptions 的 Java 17 保持一致，否则 AGP 会报
// "Inconsistent JVM-target compatibility detected"。
kotlin {
    compilerOptions {
        jvmTarget.set(JvmTarget.JVM_17)
    }
}

dependencies {
    // 只为 FileProvider（把生成的 MP3 安全地分享给其它 App）。
    // 其余界面全部使用系统原生控件，不引入任何 UI 框架依赖。
    implementation("androidx.core:core:1.13.1")
}

// ---------------------------------------------------------------------------
// Chaquopy：把 Python 运行时和依赖打进 APK
//
//   ★ Python 版本必须用 3.13，不能用 3.10（这是实测 Chaquopy 仓库得出的结论）：
//     仓库 https://chaquo.com/pypi-13.1/ 里各版本的 cp 标签分布是——
//        cp310 : aiohttp 3.10.10 / yarl 1.4.2 / multidict 5.1.0 / frozenlist 1.2.0
//        cp313 : aiohttp 3.10.10 / yarl 1.16.0 / multidict 6.1.0 / frozenlist 1.4.1
//     aiohttp 3.10.10 要求 yarl>=1.12，而 cp310 下 yarl 最高只有 1.4.2
//     ⇒ 在 3.10 上依赖解析会失败；cp313 下四个包齐全且互相满足，一次装成。
//
//   - buildPython 必须与上面的 3.13 一致（CI 里由 setup-python 提供 python3.13）
//   - Chaquopy 的原生库都是预编译好的，无需安装 Android NDK
//   - Chaquopy 17 官方要求：minSdk >= 24 ✓，AGP 在 7.3.x ~ 9.2.x 之间 ✓（本项目 8.7.3）
// ---------------------------------------------------------------------------
chaquopy {
    defaultConfig {
        version = "3.13"
        buildPython("python3.13")

        pip {
            install("edge-tts==7.2.8")
        }

        // 开发期保留 .py 源码，异常堆栈可读（发布时可改回 true 提速启动）
        pyc {
            src = false
        }
    }
}
