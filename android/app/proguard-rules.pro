# Chaquo 与 WebView 不需要额外 keep 规则，但 Python 反射调用 Kotlin 方法，
# 所以要保住 bridge 类的方法名。
-keep class io.github.magiasaveeditor.android.AndroidBridge { *; }
-keep class io.github.magiasaveeditor.android.MainActivity { *; }