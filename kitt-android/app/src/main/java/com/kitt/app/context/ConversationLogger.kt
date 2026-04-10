package com.kitt.app.context

import android.util.Log
import com.kitt.app.BuildConfig
import kotlinx.coroutines.*
import kotlinx.serialization.json.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.util.UUID
import java.util.concurrent.TimeUnit

/**
 * Gemini Live Audioの会話ログをBQに保存
 *
 * バッファリング: 30秒ごとまたは50件溜まったらバッチ送信
 * CF /conversationLog に POST
 */
class ConversationLogger {

    companion object {
        private const val TAG = "ConvLogger"
        private const val FLUSH_INTERVAL_MS = 30_000L
        private const val FLUSH_THRESHOLD = 50
    }

    val sessionId: String = "sess_${UUID.randomUUID().toString().take(8)}"
    private val buffer = mutableListOf<JsonObject>()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var flushJob: Job? = null

    private val client = OkHttpClient.Builder()
        .connectTimeout(5, TimeUnit.SECONDS)
        .readTimeout(10, TimeUnit.SECONDS)
        .build()

    fun start() {
        flushJob = scope.launch {
            while (isActive) {
                delay(FLUSH_INTERVAL_MS)
                flush()
            }
        }
        Log.d(TAG, "ConversationLogger started, session=$sessionId")
    }

    fun logUser(text: String, offerContext: String? = null) {
        addEntry("user", text, offerContext = offerContext)
    }

    fun logAssistant(text: String, offerContext: String? = null) {
        addEntry("assistant", text, offerContext = offerContext)
    }

    fun logToolCall(name: String, args: String?, result: String?) {
        addEntry("system", "tool:$name", toolCall = args, toolResult = result)
    }

    private fun addEntry(
        role: String, text: String,
        toolCall: String? = null, toolResult: String? = null,
        offerContext: String? = null
    ) {
        synchronized(buffer) {
            buffer.add(buildJsonObject {
                put("session_id", sessionId)
                put("role", role)
                put("text", text)
                toolCall?.let { put("tool_call", it) }
                toolResult?.let { put("tool_result", it) }
                offerContext?.let { put("offer_context", it) }
            })
        }
        if (buffer.size >= FLUSH_THRESHOLD) {
            scope.launch { flush() }
        }
    }

    suspend fun flush() {
        val entries: List<JsonObject>
        synchronized(buffer) {
            if (buffer.isEmpty()) return
            entries = buffer.toList()
            buffer.clear()
        }

        try {
            val body = buildJsonObject {
                putJsonArray("entries") {
                    entries.forEach { add(it) }
                }
            }

            val request = Request.Builder()
                .url("${BuildConfig.CF_BASE_URL}/conversationLog")
                .addHeader("X-API-Key", BuildConfig.CF_API_KEY)
                .addHeader("Content-Type", "application/json")
                .post(body.toString().toRequestBody("application/json".toMediaType()))
                .build()

            val response = client.newCall(request).execute()
            Log.d(TAG, "Flushed ${entries.size} entries: ${response.code}")
        } catch (e: Exception) {
            Log.e(TAG, "Flush failed, re-buffering ${entries.size} entries", e)
            synchronized(buffer) {
                buffer.addAll(0, entries) // 失敗分を先頭に戻す
            }
        }
    }

    fun destroy() {
        scope.launch {
            flush() // 最後にバッファを送信
            flushJob?.cancel()
            scope.cancel()
        }
    }
}
