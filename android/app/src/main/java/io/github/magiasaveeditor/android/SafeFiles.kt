package io.github.magiasaveeditor.android

import android.content.Context
import android.net.Uri
import android.provider.OpenableColumns
import java.io.File
import java.io.FileOutputStream

/**
 * 把 SAF 给的 content:// 复制成真实文件，因为 Python 的 open() 只认路径。
 *
 * 方向很重要：
 *  - 读（导入存档）：从 Uri 读到 `cacheDir/inbox/`，Python 打开后由 /api/import 再拷进工作区。
 *  - 写（另存为）：系统只给一个 Uri，Python 写不了；所以先让 Python 写到 `cacheDir/outbox/`，
 *    再由 [persistOutbox] 把内容推回 Uri。
 */
object SafeFiles {

    fun materialize(context: Context, uri: Uri, ensureZip: Boolean): String {
        val name = displayName(context, uri) ?: ("picked-" + System.currentTimeMillis() + if (ensureZip) ".zip" else "")
        val dir = File(context.cacheDir, "inbox").apply { mkdirs() }
        val target = uniqueFile(dir, if (ensureZip && !name.lowercase().endsWith(".zip")) "$name.zip" else name)
        context.contentResolver.openInputStream(uri).use { input ->
            requireNotNull(input) { "无法读取所选文件" }
            FileOutputStream(target).use { output ->
                input.copyTo(output)
            }
        }
        return target.absolutePath
    }

    /** 把 outbox 里写好的文件写回到用户选的保存位置。 */
    fun persistOutbox(context: Context, outboxPath: String, target: Uri): Boolean {
        val source = File(outboxPath)
        if (!source.isFile) return false
        return try {
            context.contentResolver.openOutputStream(target, "wt").use { output ->
                requireNotNull(output) { "无法写入所选位置" }
                source.inputStream().use { it.copyTo(output) }
            }
            true
        } catch (error: Exception) {
            false
        }
    }

    private fun displayName(context: Context, uri: Uri): String? {
        return try {
            context.contentResolver.query(uri, null, null, null, null)?.use { cursor ->
                val index = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                if (index >= 0 && cursor.moveToFirst()) cursor.getString(index) else null
            }
        } catch (error: Exception) {
            null
        }
    }

    private fun uniqueFile(dir: File, name: String): File {
        val safe = name.replace('/', '_').replace('\\', '_')
        var target = File(dir, safe)
        if (!target.exists()) return target
        val stem = safe.substringBeforeLast('.', safe)
        val ext = safe.substringAfterLast('.', "")
        var index = 1
        while (target.exists()) {
            target = File(dir, if (ext.isEmpty()) "$stem-$index" else "$stem-$index.$ext")
            index += 1
        }
        return target
    }
}