package io.github.magiasaveeditor.android

import android.content.Context
import android.content.res.AssetManager
import java.io.File
import java.io.FileOutputStream

/**
 * 把 APK 里的 `assets/bundle/{data,web,assets}` 解到 `filesDir/bundle`。
 *
 * 为什么要解：Python 里 `open()` 读不了 APK 内的 assets，必须先是真实文件。
 * data + assets 约 45 MB，assets 目录下多为 png，首次启动一般 2–5 秒。
 *
 * 用 `version.txt` 里记的版本号做缓存键：升级 APK 时版本号变了就重解，
 * 否则直接复用，第二次启动是瞬时的。
 */
object BundleInstaller {

    private const val VERSION = "1"          // 改 bundle 内容时 +1
    private const val MARKER = "version.txt"

    interface Progress {
        fun onProgress(done: Long, total: Long)
    }

    fun ensure(context: Context, progress: Progress? = null): File {
        val root = File(context.filesDir, "bundle")
        val marker = File(root, MARKER)
        val wanted = "$VERSION\n"
        if (marker.isFile && marker.readText() == wanted && File(root, "data").isDirectory) {
            return root
        }

        // 先解到临时目录再改名，避免中途被杀留下半套数据。
        val staging = File(context.filesDir, "bundle.tmp")
        if (staging.exists()) staging.deleteRecursively()
        staging.mkdirs()

        val assets = context.assets
        val total = countTotal(assets, "bundle", 0L).coerceAtLeast(1L)
        var done = 0L
        copyTree(assets, "bundle", staging) { delta ->
            done += delta
            progress?.onProgress(done, total)
        }

        File(staging, MARKER).writeText(wanted)
        if (root.exists()) root.deleteRecursively()
        staging.renameTo(root)
        return root
    }

    private fun countTotal(assets: AssetManager, path: String, acc: Long): Long {
        val children = try {
            assets.list(path) ?: return acc
        } catch (error: Exception) {
            return acc
        }
        if (children.isEmpty()) {
            return try {
                acc + assets.openFd(path).length
            } catch (error: Exception) {
                acc + assets.open(path).use { it.available().toLong() }
            }
        }
        var sum = acc
        for (child in children) sum = countTotal(assets, "$path/$child", sum)
        return sum
    }

    private fun copyTree(assets: AssetManager, assetPath: String, target: File, onBytes: (Long) -> Unit) {
        val children = try {
            assets.list(assetPath)
        } catch (error: Exception) {
            null
        } ?: return

        if (children.isEmpty()) {
            target.parentFile?.mkdirs()
            assets.open(assetPath).use { input ->
                FileOutputStream(target).use { output ->
                    val buffer = ByteArray(64 * 1024)
                    while (true) {
                        val read = input.read(buffer)
                        if (read <= 0) break
                        output.write(buffer, 0, read)
                        onBytes(read.toLong())
                    }
                }
            }
            return
        }

        target.mkdirs()
        for (child in children) {
            copyTree(assets, "$assetPath/$child", File(target, child), onBytes)
        }
    }
}