package io.github.magiasaveeditor.android

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.provider.OpenableColumns
import android.util.Log
import android.view.View
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import java.io.File
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/**
 * 唯一界面：一个进度提示 + 一个装本地网页的 WebView。
 *
 * 启动顺序：
 *   1. 把 APK 里的 assets/bundle/{data,web,assets} 解到 filesDir/bundle
 *   2. 设 MAGIA_* 环境变量，启动 Python，注入 AndroidBridge
 *   3. 调 magiasave.android_main.start_in_thread() 拿端口
 *   4. WebView 打开 http://127.0.0.1:<port>/
 *
 * 文件读写全部走系统文件选择器（SAF）：
 *   - 导入：Uri → cacheDir/inbox/xxx.zip → 交给 Python 的 /api/import 拷进工作区
 *   - 另存为：先给 Python 一个 cacheDir/outbox/xxx.zip，写完后由 [finishSave] 推回 Uri
 */
class MainActivity : AppCompatActivity(), AndroidBridge.HostHolder {

    private var bridge: AndroidBridge? = null

    private lateinit var statusText: TextView
    private lateinit var progress: ProgressBar
    private lateinit var retryButton: Button
    private lateinit var container: LinearLayout
    private var webView: WebView? = null

    @Volatile private var pendingPick: PickRequest? = null
    /** 用户选好的「另存为」目标 Uri，等 Python 写完再推上去。 */
    @Volatile private var pendingSaveUri: Uri? = null

    private val openDocument = registerForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        finishOpen(uri)
    }

    private val createDocument = registerForActivityResult(ActivityResultContracts.CreateDocument("application/zip")) { uri ->
        finishCreate(uri)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        bridge = AndroidBridge(this)
        buildUi()
        startEverything()
    }

    // ------------------------------------------------------------------ UI

    private fun buildUi() {
        container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(48, 48, 48, 48)
        }
        statusText = TextView(this).apply {
            text = "正在准备离线数据…"
            textSize = 16f
        }
        progress = ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal).apply {
            isIndeterminate = true
        }
        retryButton = Button(this).apply {
            text = "重试"
            visibility = View.GONE
            setOnClickListener {
                visibility = View.GONE
                startEverything()
            }
        }
        container.addView(statusText)
        container.addView(progress)
        container.addView(retryButton)
        setContentView(container)
    }

    private fun showWeb(url: String) {
        val view = WebView(this)
        view.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            allowFileAccess = false
            allowContentAccess = false
        }
        view.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val host = request.url.host ?: return false
                if (host == "127.0.0.1" || host == "localhost") return false
                startActivity(Intent(Intent.ACTION_VIEW, request.url))
                return true
            }
        }
        container.removeAllViews()
        container.addView(view, LinearLayout.LayoutParams(-1, -1))
        webView = view
        view.loadUrl(url)
    }

    private fun fail(message: String, error: Throwable? = null) {
        Log.e(TAG, message, error)
        runOnUiThread {
            statusText.text = "启动失败：$message"
            progress.visibility = View.GONE
            retryButton.visibility = View.VISIBLE
        }
    }

    // -------------------------------------------------------------- 启动

    private fun startEverything() {
        progress.visibility = View.VISIBLE
        statusText.text = "正在准备离线数据…"
        Thread {
            try {
                val bundleDir = BundleInstaller.ensure(this, object : BundleInstaller.Progress {
                    override fun onProgress(done: Long, total: Long) {
                        runOnUiThread {
                            statusText.text = "正在解包数据 ${done / 1048576} / ${total / 1048576} MB"
                        }
                    }
                })
                runOnUiThread { statusText.text = "正在启动 Python 服务…" }

                val port = PythonRuntime.start(this, bundleDir, bridge!!)
                runOnUiThread {
                    statusText.text = "正在打开界面…"
                    showWeb("http://127.0.0.1:$port/")
                }
            } catch (error: Throwable) {
                fail(error.message ?: error.javaClass.simpleName, error)
            }
        }.start()
    }

    // ---------------------------------------------------- 文件选择（SAF）

    fun requestOpenFile(): String? = requestPick(PickKind.OPEN, "")

    /**
     * 另存为：只让用户选位置，真正落盘交给 Python。
     * 返回 outbox 里准备的路径，Python 写完后调用 [finishSave] 推到 Uri。
     */
    fun requestSavePath(suggest: String): String? {
        val outbox = File(cacheDir, "outbox").apply { mkdirs() }
        val name = suggest.ifBlank { "magia-save-edited.zip" }
        val target = File(outbox, name)
        val path = requestPick(PickKind.SAVE, name) ?: return null
        // requestPick 里对 SAVE 只负责选 Uri，返回值是 outbox 路径
        return path
    }

    private fun requestPick(kind: PickKind, suggest: String): String? {
        val request = PickRequest(kind)
        pendingPick = request
        runOnUiThread {
            when (kind) {
                PickKind.OPEN -> openDocument.launch(arrayOf("application/zip", "application/octet-stream"))
                PickKind.SAVE -> createDocument.launch(suggest.ifBlank { "magia-save-edited.zip" })
            }
        }
        val ok = request.latch.await(5, TimeUnit.MINUTES)
        pendingPick = null
        return if (ok) request.path else null
    }

    private fun finishOpen(uri: Uri?) {
        val request = pendingPick ?: return
        if (uri == null) {
            request.path = null
            request.latch.countDown()
            return
        }
        try {
            // 申请长期读权限，部分云盘需要
            contentResolver.takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION)
        } catch (error: Exception) {
            // 多数本地提供者不支持，忽略
        }
        request.path = try {
            SafeFiles.materialize(this, uri, ensureZip = true)
        } catch (error: Exception) {
            Log.e(TAG, "materialize(open) failed", error)
            null
        }
        request.latch.countDown()
    }

    private fun finishCreate(uri: Uri?) {
        val request = pendingPick ?: return
        if (uri == null) {
            request.path = null
            request.latch.countDown()
            return
        }
        pendingSaveUri = uri
        val outbox = File(cacheDir, "outbox").apply { mkdirs() }
        val name = displayName(uri) ?: ("magia-save-edited-" + System.currentTimeMillis() + ".zip")
        val target = File(outbox, if (name.lowercase().endsWith(".zip")) name else "$name.zip")
        request.path = target.absolutePath
        request.latch.countDown()
    }

    /** Python 把存档写到 outbox 之后，这里把内容推回用户选的位置。 */
    fun finishSave(outboxPath: String): Boolean {
        val uri = pendingSaveUri ?: return false
        val ok = SafeFiles.persistOutbox(this, outboxPath, uri)
        pendingSaveUri = null
        return ok
    }

    fun hasPendingSave(): Boolean = pendingSaveUri != null

    private fun displayName(uri: Uri): String? {
        return try {
            contentResolver.query(uri, null, null, null, null)?.use { cursor ->
                val index = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                if (index >= 0 && cursor.moveToFirst()) cursor.getString(index) else null
            }
        } catch (error: Exception) {
            null
        }
    }

    // ------------------------------------------------- AndroidBridge 需要

    override val appContext: android.content.Context get() = applicationContext

    override fun currentActivity(): MainActivity? = this

    override fun onDestroy() {
        webView?.destroy()
        webView = null
        super.onDestroy()
    }

    private enum class PickKind { OPEN, SAVE }

    private class PickRequest(val kind: PickKind) {
        val latch = CountDownLatch(1)
        @Volatile var path: String? = null
    }

    companion object {
        private const val TAG = "MagiaSaveEditor"
    }
}