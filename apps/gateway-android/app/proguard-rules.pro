# Keep Room, Retrofit, CameraX
-keep class androidx.room.** { *; }
-keep class com.pagestoaudio.gateway.** { *; }
-keep class retrofit2.** { *; }
-keepattributes Signature, InnerClasses, EnclosingMethod
-dontwarn org.conscrypt.**
-dontwarn org.bouncycastle.**
-dontwarn org.openjsse.**
