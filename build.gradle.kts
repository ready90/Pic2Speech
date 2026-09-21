// 顶层构建脚本：只声明插件版本，具体配置在 app/build.gradle.kts
plugins {
    id("com.android.application") version "8.7.3" apply false

    // Kotlin 必须 >= 2.2，不能用 2.0.21：
    //   Kotlin 官方兼容表 https://kotlinlang.org/docs/gradle-configure-project.html
    //     KGP 2.0.20-2.0.21 -> 仅支持 AGP 7.1.3-8.5（本项目 AGP 是 8.7.3，超出范围，
    //                          构建时报 "friendPathsSet$kotlin_gradle_plugin_common"
    //                          / "Current thread does not hold the state lock for root project"）
    //     KGP 2.2.20-2.2.21 -> 支持 Gradle 7.6.3-8.14、AGP 7.3.1-8.11.1（本项目 Gradle 8.9 + AGP 8.7.3 全在范围内）
    id("org.jetbrains.kotlin.android") version "2.2.20" apply false

    id("com.chaquo.python") version "17.0.0" apply false
}
