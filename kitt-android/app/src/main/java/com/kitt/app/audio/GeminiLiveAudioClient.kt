package com.kitt.app.audio

import android.util.Base64
import android.util.Log
import com.kitt.app.BuildConfig
import com.kitt.app.offer.OfferJudgeClient
import com.kitt.app.service.KittAccessibilityService
import com.kitt.app.service.KittForegroundService
import kotlinx.coroutines.*
import kotlinx.serialization.json.*
import okhttp3.*
import java.util.concurrent.TimeUnit

/**
 * Gemini Live Audio WebSocket接続
 *
 * 既存PWAのWebSocketロジックをKotlinに移植。
 * - 音声入力: DJI MIC MINIからのPCM16データを送信
 * - 音声出力: Geminiからの音声データをAirPodsに再生
 * - テキスト: オファー情報やコンテキストの注入
 * - Function calling: メディア操作等
 */
class GeminiLiveAudioClient(
    private val audioRouter: AudioRouter
) {

    private var ws: WebSocket? = null
    private var isConnected = false
    private var isConnecting = false
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var reconnectJob: Job? = null
    private var keepaliveJob: Job? = null

    companion object {
        private const val TAG = "GeminiAudio"
        private const val MODEL = "gemini-2.5-flash-native-audio-preview-12-2025"
        private const val VOICE = "Zephyr"
        private const val RECONNECT_DELAY_MS = 2000L
        private const val KEEPALIVE_INTERVAL_MS = 300_000L // 5分
    }

    /**
     * Gemini Live Audio WebSocketに接続
     */
    suspend fun connect() {
        if (isConnected || isConnecting) return
        isConnecting = true

        val apiKey = BuildConfig.GEMINI_API_KEY
        if (apiKey.isBlank()) {
            Log.e(TAG, "GEMINI_API_KEY not set")
            isConnecting = false
            return
        }

        val url = "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent?key=$apiKey"

        val client = OkHttpClient.Builder()
            .readTimeout(0, TimeUnit.MILLISECONDS) // WebSocketは無期限
            .pingInterval(30, TimeUnit.SECONDS)
            .build()

        val request = Request.Builder().url(url).build()

        client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                Log.d(TAG, "WebSocket opened, sending setup...")
                ws = webSocket

                // Setup message (PWAと同じ構造)
                val setup = buildJsonObject {
                    putJsonObject("setup") {
                        put("model", "models/$MODEL")
                        putJsonObject("generationConfig") {
                            putJsonArray("responseModalities") { add("AUDIO") }
                            putJsonObject("speechConfig") {
                                putJsonObject("voiceConfig") {
                                    putJsonObject("prebuiltVoiceConfig") {
                                        put("voiceName", VOICE)
                                    }
                                }
                            }
                        }
                        putJsonObject("systemInstruction") {
                            putJsonArray("parts") {
                                addJsonObject { put("text", buildSystemPrompt()) }
                            }
                        }
                        putJsonArray("tools") {
                            addJsonObject {
                                putJsonArray("functionDeclarations") {
                                    // メディア操作
                                    addJsonObject {
                                        put("name", "control_media")
                                        put("description", "メディアアプリを操作する(YouTube/TVer/radiko/J:COM)")
                                        putJsonObject("parameters") {
                                            put("type", "object")
                                            putJsonObject("properties") {
                                                putJsonObject("action") {
                                                    put("type", "string")
                                                    put("description", "play/pause/stop/volume_up/volume_down/open")
                                                }
                                                putJsonObject("app") {
                                                    put("type", "string")
                                                    put("description", "youtube/tver/radiko/jcom")
                                                }
                                                putJsonObject("query") {
                                                    put("type", "string")
                                                    put("description", "検索クエリや番組名")
                                                }
                                            }
                                            putJsonArray("required") { add("action") }
                                        }
                                    }
                                    // 受諾/拒否
                                    addJsonObject {
                                        put("name", "accept_offer")
                                        put("description", "現在表示中の配達オファーを受諾する")
                                        putJsonObject("parameters") {
                                            put("type", "object")
                                            putJsonObject("properties") {}
                                        }
                                    }
                                    addJsonObject {
                                        put("name", "reject_offer")
                                        put("description", "現在表示中の配達オファーを拒否する")
                                        putJsonObject("parameters") {
                                            put("type", "object")
                                            putJsonObject("properties") {}
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                webSocket.send(setup.toString())
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                try {
                    val msg = Json.parseToJsonElement(text).jsonObject

                    // Setup完了
                    if (msg.containsKey("setupComplete")) {
                        isConnected = true
                        isConnecting = false
                        Log.d(TAG, "Gemini connected ✓")

                        // マイク開始
                        scope.launch {
                            delay(500)
                            audioRouter.startMicCapture { pcmData ->
                                sendAudioChunk(pcmData)
                            }
                        }

                        // Keepalive
                        startKeepalive()

                        // 再接続時の挨拶
                        sendText("接続が復帰しました。修治さんに短く一言声をかけてください。初対面のような挨拶はしないで。")
                        return
                    }

                    // 音声レスポンス
                    val modelParts = msg["serverContent"]
                        ?.jsonObject?.get("modelTurn")
                        ?.jsonObject?.get("parts")
                        ?.jsonArray

                    modelParts?.forEach { part ->
                        val partObj = part.jsonObject
                        // 音声データ
                        val audioData = partObj["inlineData"]?.jsonObject
                        if (audioData != null) {
                            val mimeType = audioData["mimeType"]?.jsonPrimitive?.content ?: ""
                            if (mimeType.startsWith("audio/")) {
                                val base64 = audioData["data"]?.jsonPrimitive?.content ?: ""
                                val pcm = Base64.decode(base64, Base64.DEFAULT)
                                audioRouter.playAudio(pcm)
                            }
                        }
                        // テキスト
                        val textContent = partObj["text"]?.jsonPrimitive?.content
                        if (textContent != null) {
                            handleGeminiText(textContent)
                        }
                    }

                    // ターン完了
                    val turnComplete = msg["serverContent"]?.jsonObject?.get("turnComplete")
                    if (turnComplete?.jsonPrimitive?.boolean == true) {
                        // メディア音量を元に戻す
                        audioRouter.abandonAudioFocus()
                    }

                    // Function calling
                    val toolCall = msg["toolCall"]?.jsonObject
                    if (toolCall != null) {
                        handleToolCall(toolCall)
                    }

                } catch (e: Exception) {
                    Log.e(TAG, "WS parse error", e)
                }
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                Log.e(TAG, "WebSocket error", t)
                onDisconnected()
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                Log.d(TAG, "WebSocket closed: $code $reason")
                onDisconnected()
            }
        })
    }

    fun disconnect() {
        keepaliveJob?.cancel()
        reconnectJob?.cancel()
        audioRouter.stopMicCapture()
        ws?.close(1000, "bye")
        ws = null
        isConnected = false
    }

    /**
     * テキストメッセージ送信 (オファー情報、コンテキスト注入等)
     */
    fun sendText(text: String) {
        val msg = buildJsonObject {
            putJsonObject("clientContent") {
                putJsonArray("turns") {
                    addJsonObject {
                        put("role", "user")
                        putJsonArray("parts") {
                            addJsonObject { put("text", text) }
                        }
                    }
                }
                put("turnComplete", true)
            }
        }
        ws?.send(msg.toString())
    }

    /**
     * オファー判定結果をKITTに注入して音声報告させる
     */
    fun sendOfferContext(judgment: OfferJudgeClient.JudgmentResult) {
        audioRouter.requestAudioFocusForSpeech()

        val prompt = buildString {
            append("【配達オファー判定結果】\n")
            append("アプリ: ${judgment.app}\n")
            append("判定: ${judgment.decision}\n")
            append("報酬: ¥${judgment.reward}\n")
            append("推定時給: ¥${judgment.estimatedHourlyRate}/h\n")
            append("実効時給: ¥${judgment.effectiveHourlyRate}/h\n")
            append("店名: ${judgment.storeName}\n")
            append("理由: ${judgment.reason}\n")
            append("\nこの判定結果を修治さんに音声で簡潔に報告して。")
            append("報酬、時給、店名、判断理由のポイントを伝えて。")
            append("修治さんの返答を待って、「受けて」なら受諾、「パス」なら拒否を実行する。")
        }
        sendText(prompt)
    }

    /**
     * PCM16音声チャンクをGeminiに送信
     */
    private fun sendAudioChunk(pcmData: ByteArray) {
        if (!isConnected) return
        val base64 = Base64.encodeToString(pcmData, Base64.NO_WRAP)
        val msg = buildJsonObject {
            putJsonObject("realtimeInput") {
                putJsonObject("mediaChunks") {
                    put("data", base64)
                    put("mimeType", "audio/pcm;rate=16000")
                }
            }
        }
        ws?.send(msg.toString())
    }

    /**
     * Geminiからのテキスト応答を処理
     */
    private fun handleGeminiText(text: String) {
        Log.d(TAG, "Gemini text: $text")
        // 会話記録をBQに保存
        // TODO: 会話ログの蓄積
    }

    /**
     * Function calling処理
     */
    private fun handleToolCall(toolCall: JsonObject) {
        val functionCalls = toolCall["functionCalls"]?.jsonArray ?: return
        val responses = mutableListOf<JsonObject>()

        for (fc in functionCalls) {
            val fcObj = fc.jsonObject
            val name = fcObj["name"]?.jsonPrimitive?.content ?: continue
            val args = fcObj["args"]?.jsonObject

            Log.d(TAG, "Tool call: $name args=$args")

            val result = when (name) {
                "control_media" -> {
                    val action = args?.get("action")?.jsonPrimitive?.content ?: ""
                    val app = args?.get("app")?.jsonPrimitive?.content
                    val query = args?.get("query")?.jsonPrimitive?.content
                    KittAccessibilityService.instance?.controlMedia(action, app, query)
                    "メディア操作を実行しました: $action ${app ?: ""} ${query ?: ""}"
                }
                "accept_offer" -> {
                    // 現在表示中のアプリで受諾タップ
                    val success = KittAccessibilityService.instance?.tapAcceptButton(
                        currentOfferApp ?: ""
                    ) ?: false
                    if (success) "受諾しました" else "受諾ボタンが見つかりません"
                }
                "reject_offer" -> {
                    val success = KittAccessibilityService.instance?.tapRejectButton(
                        currentOfferApp ?: ""
                    ) ?: false
                    if (success) "拒否しました" else "拒否ボタンが見つかりません"
                }
                else -> "不明なコマンド: $name"
            }

            responses.add(buildJsonObject {
                put("name", name)
                putJsonObject("response") { put("result", result) }
            })
        }

        if (responses.isNotEmpty()) {
            val responseMsg = buildJsonObject {
                putJsonObject("toolResponse") {
                    putJsonArray("functionResponses") {
                        responses.forEach { add(it) }
                    }
                }
            }
            ws?.send(responseMsg.toString())
        }
    }

    private var currentOfferApp: String? = null

    fun setCurrentOfferApp(app: String) {
        currentOfferApp = app
    }

    private fun onDisconnected() {
        isConnected = false
        isConnecting = false
        audioRouter.stopMicCapture()
        keepaliveJob?.cancel()

        // 自動再接続 (2秒後)
        reconnectJob = scope.launch {
            delay(RECONNECT_DELAY_MS)
            Log.d(TAG, "Auto-reconnecting...")
            connect()
        }
    }

    private fun startKeepalive() {
        keepaliveJob?.cancel()
        keepaliveJob = scope.launch {
            while (isActive) {
                delay(KEEPALIVE_INTERVAL_MS)
                if (isConnected) {
                    Log.d(TAG, "Keepalive reconnect")
                    disconnect()
                    delay(1000)
                    connect()
                }
            }
        }
    }

    private fun buildSystemPrompt(): String {
        val now = java.text.SimpleDateFormat("yyyy-MM-dd HH:mm", java.util.Locale.JAPAN).apply {
            timeZone = java.util.TimeZone.getTimeZone("Asia/Tokyo")
        }.format(java.util.Date())

        return """
あなたはKITT。修治(しゅうじ)さんの個人AIエージェント。
AirPodsの向こう側にいる相棒。常に寄り添い、自然な会話をする。

現在時刻: $now (JST)

## 役割
- フードデリバリー(Uber/出前館/ロケットナウ/menu)の配達判定と自動操作
- オファーが来たら判定結果を音声で報告し、修治さんの指示で受諾/拒否を実行
- 稼働サポート: トイレ・食事・水分・ガソリンのタイミング提案
- メディア操作: 「ラジコつけて」「YouTube止めて」→ function callingで実行
- 情報提供: 天気変化、交通情報、ニュース、X投稿の要約
- 収支管理: 今日の稼ぎ、目標達成状況、引き落とし予定
- 健康管理: 体重推移、血圧、疲労度からの稼働アドバイス
- 何でも対応: 質問、指示、相談

## 話し方
- 自然な日本語で、簡潔すぎず自然体
- 「修治さん」と呼ぶ
- 本音で話す、お世辞は言わない

## 重要ルール
- オファー判定中は最優先。他の話題は後回し
- メディアアプリの操作はfunction callingで実行
- 受諾/拒否もfunction callingで実行
- 修治さんの声が聞き取れなかったら聞き返す
        """.trimIndent()
    }
}
