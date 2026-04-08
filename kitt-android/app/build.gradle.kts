plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.serialization")
    id("org.jetbrains.kotlin.plugin.compose")
}

android {
    namespace = "com.kitt.app"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.kitt.app"
        minSdk = 31 // Android 12+ (Pixel 10 Pro)
        targetSdk = 35
        versionCode = 1
        versionName = "1.0.0"

        // API keys from local.properties or CI
        buildConfigField("String", "GEMINI_API_KEY", "\"${project.findProperty("GEMINI_API_KEY") ?: ""}\"")
        buildConfigField("String", "CF_API_KEY", "\"${project.findProperty("CF_API_KEY") ?: ""}\"")
        buildConfigField("String", "CF_BASE_URL", "\"https://asia-northeast1-gen-lang-client-0549297663.cloudfunctions.net\"")
        buildConfigField("String", "FIREBASE_RTDB_URL", "\"https://ubereats-kitt-default-rtdb.asia-southeast1.firebasedatabase.app\"")
        buildConfigField("String", "FIREBASE_DB_SECRET", "\"${project.findProperty("FIREBASE_DB_SECRET") ?: ""}\"")
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
        debug {
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    // composeOptions managed by kotlin-compose plugin
}

dependencies {
    // Kotlin
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.7.3")

    // AndroidX Core
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    implementation("androidx.lifecycle:lifecycle-service:2.8.7")
    implementation("androidx.activity:activity-compose:1.9.3")

    // Jetpack Compose
    implementation(platform("androidx.compose:compose-bom:2024.12.01"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-graphics")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.ui:ui-tooling-preview")
    debugImplementation("androidx.compose.ui:ui-tooling")

    // OkHttp (WebSocket for Gemini Live Audio)
    implementation("com.squareup.okhttp3:okhttp:4.12.0")

    // Location
    implementation("com.google.android.gms:play-services-location:21.3.0")

    // Firebase (RTDB for real-time sync with iPhone nav)
    implementation(platform("com.google.firebase:firebase-bom:33.7.0"))
    implementation("com.google.firebase:firebase-database-ktx")

    // DataStore (preferences)
    implementation("androidx.datastore:datastore-preferences:1.1.1")
}
