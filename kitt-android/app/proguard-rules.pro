# KITT Android ProGuard Rules

# OkHttp
-dontwarn okhttp3.**
-dontwarn okio.**
-keep class okhttp3.** { *; }

# kotlinx.serialization
-keepattributes *Annotation*, InnerClasses
-dontnote kotlinx.serialization.AnnotationsKt
-keepclassmembers class kotlinx.serialization.json.** { *** Companion; }
-keepclasseswithmembers class kotlinx.serialization.json.** {
    kotlinx.serialization.KSerializer serializer(...);
}

# Firebase
-keep class com.google.firebase.** { *; }

# Google Play Services Location
-keep class com.google.android.gms.location.** { *; }

# KITT data classes (used in JSON serialization)
-keep class com.kitt.app.offer.OfferJudgeClient$JudgmentResult { *; }
-keep class com.kitt.app.service.KittAccessibilityService$OfferData { *; }
-keep class com.kitt.app.ui.MainActivity$NotificationLog { *; }

# BuildConfig
-keep class com.kitt.app.BuildConfig { *; }
