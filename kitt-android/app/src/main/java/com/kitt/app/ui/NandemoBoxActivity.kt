package com.kitt.app.ui

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.util.Base64
import android.util.Log
import android.widget.Toast
import androidx.activity.ComponentActivity
import com.kitt.app.BuildConfig
import kotlinx.coroutines.*
import kotlinx.serialization.json.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.util.concurrent.TimeUnit

/**
 * 他アプリからの共有インテントを受信して何でもBOXに送信
 *
 * ギャラリーの写真、テキスト、URLなどを受け取り
 * CF nandemoBox に送信 → BQに保存
 */
class NandemoBoxActivity : ComponentActivity() {

    companion object {
        private const val TAG = "NandemoBox"
    }

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val client = OkHttpClient.Builder()
        .connectTimeout(5, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .build()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        when (intent?.action) {
            Intent.ACTION_SEND -> handleSend(intent)
            else -> {
                Toast.makeText(this, "不明なインテント", Toast.LENGTH_SHORT).show()
                finish()
            }
        }
    }

    private fun handleSend(intent: Intent) {
        val mimeType = intent.type ?: ""
        Toast.makeText(this, "KITTに送信中...", Toast.LENGTH_SHORT).show()

        scope.launch {
            try {
                when {
                    mimeType.startsWith("image/") -> {
                        val imageUri = intent.getParcelableExtra<Uri>(Intent.EXTRA_STREAM)
                        if (imageUri != null) {
                            sendImage(imageUri)
                        }
                    }
                    mimeType == "text/plain" -> {
                        val text = intent.getStringExtra(Intent.EXTRA_TEXT) ?: ""
                        if (text.isNotEmpty()) {
                            sendText(text)
                        }
                    }
                    else -> {
                        Log.w(TAG, "Unsupported mime type: $mimeType")
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Send failed", e)
                withContext(Dispatchers.Main) {
                    Toast.makeText(this@NandemoBoxActivity, "送信失敗: ${e.message}", Toast.LENGTH_SHORT).show()
                }
            }
            withContext(Dispatchers.Main) {
                finish()
            }
        }
    }

    private suspend fun sendImage(uri: Uri) {
        val inputStream = contentResolver.openInputStream(uri) ?: return
        val bytes = inputStream.readBytes()
        inputStream.close()
        val base64 = Base64.encodeToString(bytes, Base64.NO_WRAP)

        val body = buildJsonObject {
            put("image_base64", base64)
            put("source", "android_share")
        }

        val request = Request.Builder()
            .url("${BuildConfig.CF_BASE_URL}/nandemoBox")
            .addHeader("X-API-Key", BuildConfig.CF_API_KEY)
            .addHeader("Content-Type", "application/json")
            .post(body.toString().toRequestBody("application/json".toMediaType()))
            .build()

        val response = client.newCall(request).execute()
        val responseBody = response.body?.string()
        Log.d(TAG, "Image sent: ${response.code} $responseBody")

        withContext(Dispatchers.Main) {
            Toast.makeText(this@NandemoBoxActivity, "KITTに送信完了", Toast.LENGTH_SHORT).show()
        }

        // KITTに通知
        com.kitt.app.service.KittForegroundService.instance?.geminiClient?.sendText(
            "何でもBOXに画像が送信されました。"
        )
    }

    private suspend fun sendText(text: String) {
        val body = buildJsonObject {
            put("ocr_text", text)
            put("source", "android_share")
        }

        val request = Request.Builder()
            .url("${BuildConfig.CF_BASE_URL}/nandemoBox")
            .addHeader("X-API-Key", BuildConfig.CF_API_KEY)
            .addHeader("Content-Type", "application/json")
            .post(body.toString().toRequestBody("application/json".toMediaType()))
            .build()

        val response = client.newCall(request).execute()
        Log.d(TAG, "Text sent: ${response.code}")

        withContext(Dispatchers.Main) {
            Toast.makeText(this@NandemoBoxActivity, "KITTに送信完了", Toast.LENGTH_SHORT).show()
        }

        com.kitt.app.service.KittForegroundService.instance?.geminiClient?.sendText(
            "何でもBOXにテキストが送信されました: ${text.take(100)}"
        )
    }

    override fun onDestroy() {
        scope.cancel()
        super.onDestroy()
    }
}
