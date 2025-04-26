import org.jetbrains.kotlin.gradle.tasks.KotlinCompile
import org.gradle.api.tasks.testing.Test
import org.gradle.api.tasks.compile.JavaCompile

plugins {
    id("com.android.application")
    // START: FlutterFire Configuration
    id("com.google.gms.google-services")
    // END: FlutterFire Configuration
    id("kotlin-android")
    id("dev.flutter.flutter-gradle-plugin")
}

android {
    ndkVersion = "27.0.12077973"
    namespace = "com.example.stream_alert"
    compileSdk = flutter.compileSdkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
        isCoreLibraryDesugaringEnabled = true
    }

    kotlinOptions {
        jvmTarget = "11"
    }

    configurations.all {
        exclude(group = "com.aboutyou.dart_packages.sign_in_with_apple", module = "sign_in_with_apple")
    }

    defaultConfig {
        applicationId = "com.example.stream_alert"
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    buildTypes {
        release {
            signingConfig = signingConfigs.getByName("debug")
        }
    }

    dependencies {
        coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.1.5")
        
        // 테스트 관련
        testImplementation("junit:junit:4.13.2")
        testImplementation("org.robolectric:robolectric:4.12.2")
        testImplementation("androidx.test:core:1.5.0")
        testImplementation("androidx.test.ext:junit:1.1.5")
        testImplementation("androidx.test:runner:1.5.2")

        implementation("androidx.core:core-ktx:1.10.1")
        implementation("androidx.appcompat:appcompat:1.6.1")

        implementation(platform("com.google.firebase:firebase-bom:32.0.0"))
        implementation("com.google.firebase:firebase-messaging")
    }
}

flutter {
    source = "../.."
}

tasks.withType<Test>().configureEach {
    if (name.contains("flutter_local_notifications")) {
        enabled = false
    }
}

tasks.withType<KotlinCompile> {
    kotlinOptions {
        jvmTarget = "11"
    }
}

// 📌 빌드 경고 무시 설정
tasks.withType<JavaCompile> {
    options.compilerArgs.addAll(
        listOf(
            "-Xlint:-options",
            "-Xlint:-deprecation", 
            "-Xlint:-unchecked"
        )
    )
}
