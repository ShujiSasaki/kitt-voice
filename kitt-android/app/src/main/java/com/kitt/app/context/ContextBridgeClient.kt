package com.kitt.app.context

import android.util.Log
import com.kitt.app.BuildConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.*
import okhttp3.OkHttpClient
import okhttp3.Request
import java.util.concurrent.TimeUnit

/**
 * CF /contextBridge から文脈を取得
 *
 * 再接続時: 今日の全履歴 + 会話サマリー + 天気
 * オファー判定前: 最小文脈 (3秒以内)
 */
class ContextBridgeClient {

    companion object {
        private const val TAG = "ContextBridge"
    }

    private val client = OkHttpClient.Builder()
        .connectTimeout(5, TimeUnit.SECONDS)
        .readTimeout(10, TimeUnit.SECONDS)
        .build()

    /**
     * 再接続時の文脈取得 → システムプロンプトに注入する文字列を生成
     */
    suspend fun fetchReconnectContext(): String {
        return withContext(Dispatchers.IO) {
            try {
                val request = Request.Builder()
                    .url("${BuildConfig.CF_BASE_URL}/contextBridge?mode=reconnect")
                    .addHeader("X-API-Key", BuildConfig.CF_API_KEY)
                    .build()

                val response = client.newCall(request).execute()
                val body = response.body?.string() ?: return@withContext ""
                if (!response.isSuccessful) {
                    Log.e(TAG, "contextBridge error: ${response.code} $body")
                    return@withContext ""
                }

                val json = Json.parseToJsonElement(body).jsonObject
                buildContextPrompt(json)
            } catch (e: Exception) {
                Log.e(TAG, "fetchReconnectContext failed", e)
                ""
            }
        }
    }

    /**
     * オファー判定用の最小文脈取得
     */
    suspend fun fetchOfferContext(): JsonObject? {
        return withContext(Dispatchers.IO) {
            try {
                val request = Request.Builder()
                    .url("${BuildConfig.CF_BASE_URL}/contextBridge?mode=offer")
                    .addHeader("X-API-Key", BuildConfig.CF_API_KEY)
                    .build()

                val response = client.newCall(request).execute()
                val body = response.body?.string() ?: return@withContext null
                if (!response.isSuccessful) return@withContext null

                Json.parseToJsonElement(body).jsonObject
            } catch (e: Exception) {
                Log.e(TAG, "fetchOfferContext failed", e)
                null
            }
        }
    }

    private fun buildContextPrompt(json: JsonObject): String {
        val sb = StringBuilder()
        sb.appendLine("\n\n## 現在の稼働状況")

        // 今日の統計
        json["todayStats"]?.jsonObject?.let { stats ->
            val earnings = stats["total_earnings"]?.jsonPrimitive?.intOrNull ?: 0
            val deliveries = stats["actual_deliveries"]?.jsonPrimitive?.intOrNull ?: 0
            val offers = stats["total_offers"]?.jsonPrimitive?.intOrNull ?: 0
            val accepted = stats["accepted"]?.jsonPrimitive?.intOrNull ?: 0
            val avgHourly = stats["avg_hourly_rate"]?.jsonPrimitive?.intOrNull ?: 0
            sb.appendLine("今日の稼ぎ: ¥$earnings ($deliveries 件配達)")
            sb.appendLine("オファー: ${offers}件中 ${accepted}件受諾")
            if (avgHourly > 0) sb.appendLine("平均時給: ¥$avgHourly")
        }

        // 天気
        json["weather"]?.jsonObject?.let { weather ->
            val condition = weather["condition"]?.jsonPrimitive?.content ?: ""
            val temp = weather["temperature"]?.jsonPrimitive?.doubleOrNull
            if (condition.isNotEmpty()) {
                sb.appendLine("天気: $condition${if (temp != null) " ${temp}°C" else ""}")
            }
        }

        // クエスト
        json["quests"]?.jsonArray?.let { quests ->
            if (quests.isNotEmpty()) {
                sb.appendLine("未完了クエスト:")
                quests.take(3).forEach { q ->
                    val summary = q.jsonObject["summary"]?.jsonPrimitive?.content ?: ""
                    if (summary.isNotEmpty()) sb.appendLine("  - $summary")
                }
            }
        }

        // 直近オファー
        json["recentOffers"]?.jsonArray?.let { offers ->
            if (offers.isNotEmpty()) {
                sb.appendLine("直近のオファー:")
                offers.take(5).forEach { o ->
                    val obj = o.jsonObject
                    val store = obj["store_name"]?.jsonPrimitive?.content ?: "?"
                    val reward = obj["offer_reward"]?.jsonPrimitive?.intOrNull ?: 0
                    val decision = obj["gemini_decision"]?.jsonPrimitive?.content ?: "?"
                    val time = obj["time_jst"]?.jsonPrimitive?.content ?: ""
                    sb.appendLine("  - [$time] $store ¥$reward → $decision")
                }
            }
        }

        // 会話サマリー
        json["conversations"]?.jsonArray?.let { convs ->
            if (convs.isNotEmpty()) {
                sb.appendLine("直近の会話:")
                convs.take(10).forEach { c ->
                    val obj = c.jsonObject
                    val role = obj["role"]?.jsonPrimitive?.content ?: "?"
                    val text = obj["text"]?.jsonPrimitive?.content ?: ""
                    val time = obj["time_jst"]?.jsonPrimitive?.content ?: ""
                    val speaker = if (role == "user") "修治さん" else "KITT"
                    sb.appendLine("  [$time] $speaker: $text")
                }
            }
        }

        return sb.toString()
    }
}
