package io.github.magiasaveeditor.android

import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.core.content.FileProvider
import java.io.File

/**
 * Python 侧 `magiasave/bridge.py` 的宿主实现。
 *
 * Chaquo 允许把 Kotlin 对象直接传给 Python，再由
 * `magiasave.android_main.start_in_thread(..., py_host=bridge)` 注入，
 * Python 调 `host.pickFile(mode, suggest, initial)` 时就会回到这里。
 *
 * 线程约束：这些方法在 Python 的 HTTP handler 线程上被调用，而内部要等 UI 线程的
 * ActivityResult 回调，所以用 CountDownLatch 阻塞；调用方必须是非主线程。
 */
class AndroidBridge(private val host: HostHolder) {

    interface HostHolder {
        val appContext: Context
        fun currentActivity(): MainActivity?
    }

    fun bridgeVersion(): String = "1"

    /**
     * mode: open / save。
     *  - open：返回用户所选文件被复制出来的真实路径（cacheDir/inbox/…）
     *  - save：返回 outbox 里的目标路径，Python 写完后调 [commitSave] 才真正落盘
     * 用户取消返回 null。
     */
    fun pickFile(mode: String, suggest: String, initial: String): String? {
        val activity = host.currentActivity() ?: return null
        return when (mode) {
            "save" -> activity.requestSavePath(suggest)
            else -> activity.requestOpenFile()
        }
    }

    /**
     * 让 Python 在「另存为」写完后调用：把 outbox 文件推回用户选的 Uri。
     */
    fun commitSave(path: String): Boolean {
        val activity = host.currentActivity() ?: return false
        if (!activity.hasPendingSave()) return false
        return activity.finishSave(path)
    }

    /** 交给系统分享面板（微信 / 网盘 / 文件管理器都能接）。 */
    fun shareFile(path: String): Boolean {
        val activity = host.currentActivity() ?: return false
        val file = File(path)
        if (!file.isFile) return false
        val intent = Intent(Intent.ACTION_SEND).apply {
            type = "application/zip"
            putExtra(Intent.EXTRA_STREAM, uriFor(file))
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        activity.runOnUiThread {
            activity.startActivity(Intent.createChooser(intent, "分享存档"))
        }
        return true
    }

    /** 用系统默认应用打开（比如交给压缩软件看看内容）。 */
    fun openFile(path: String): Boolean {
        val activity = host.currentActivity() ?: return false
        val file = File(path)
        if (!file.isFile) return false
        val intent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uriFor(file), "application/zip")
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        return try {
            activity.runOnUiThread { activity.startActivity(intent) }
            true
        } catch (error: Exception) {
            false
        }
    }

    private fun uriFor(file: File): Uri =
        FileProvider.getUriForFile(
            host.appContext,
            host.appContext.packageName + AUTHORITY_SUFFIX,
            file
        )

    companion object {
        const val AUTHORITY_SUFFIX = ".fileprovider"
    }
}