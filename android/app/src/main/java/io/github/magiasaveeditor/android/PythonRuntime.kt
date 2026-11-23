package io.github.magiasaveeditor.android

import android.content.Context
import android.util.Log
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import java.io.File

/**
 * 启动 Chaquo Python，把 magiasave 包设成可导入，再调用 android_main.start_in_thread()。
 *
 * 只启动一次：WebView 重试时不会重复初始化解释器（Chaquo 重复 start 会抛异常）。
 */
object PythonRuntime {

    private const val TAG = "MagiaSaveEditor"
    @Volatile private var started = false

    @Synchronized
    fun start(activity: MainActivity, bundleDir: File, bridge: AndroidBridge): Int {
        if (!Python.isStarted()) {
            Python.start(AndroidPlatform(activity))
        }
        started = true

        val appDir = File(activity.filesDir, "workspace")
        appDir.mkdirs()

        // Chaquo 的 sys.path 里有 assets/chaquopy/app.imy，源码已同步进去；
        // 这里再把 bundle 根挂上，保证 paths.bundle_root() 与 app_dir() 和 Kotlin 一致。
        val python = Python.getInstance()
        val sys = python.getModule("sys")
        sys.callAttr("setrecursionlimit", 20000)

        val env = python.getModule("os").get("environ")
        env.callAttr("__setitem__", "MAGIA_BUNDLE_ROOT", bundleDir.absolutePath)
        env.callAttr("__setitem__", "MAGIA_APP_DIR", appDir.absolutePath)
        env.callAttr("__setitem__", "MAGIA_ANDROID", "1")

        val module = python.getModule("magiasave.android_main")
        val port = module.callAttr(
            "start_in_thread",
            "127.0.0.1",
            0,
            null,
            bridge
        ).toInt()

        Log.i(TAG, "python serving on 127.0.0.1:$port, bundle=$bundleDir, app=$appDir")
        return port
    }
}