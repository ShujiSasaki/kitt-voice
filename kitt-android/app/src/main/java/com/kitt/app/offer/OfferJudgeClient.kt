package com.kitt.app.offer

import android.util.Log
import com.kitt.app.BuildConfig
import com.kitt.app.service.KittAccessibilityService
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.util.concurrent.TimeUnit

/**
 * Cloud Functions offerJudge との通信
 *
 * AccessibilityServiceから取得した構造化データを送信し、判定結果を受信。
 * OCRパースは不要 — 直接構造化データを送る。
 */
class OfferJudgeClient {

    private val client = OkHttpClient.Builder()
        .connectTimeout(5, TimeUnit.SECONDS)
        .readTimeout(10, TimeUnit.SECONDS)
        .build()

    companion object {
        private const val TAG = "OfferJudge"
    }

    /**
     * オファーデータをCFに送信して判定を取得
     */
    suspend fun judge(offer: KittAccessibilityService.OfferData): JudgmentResult? {
        return withContext(Dispatchers.IO) {
            try {
                val body = buildJsonObject {
                    // 構造化データ (OCR不要)
                    put("source", "accessibility_service")
                    put("app", offer.app)
                    offer.reward?.let { put("reward", it) }
                    offer.distance?.let { put("distance", it) }
                    offer.duration?.let { put("duration", it) }
                    offer.storeName?.let { put("storeName", it) }
                    offer.dropoffAddress?.let { put("dropoffAddress", it) }
                    put("rawText", offer.rawText)

                    // GPS (KittForegroundServiceから取得)
                    // TODO: 現在地の緯度経度を注入
                    // put("lat", currentLat)
                    // put("lng", currentLng)
                }

                val request = Request.Builder()
                    .url("${BuildConfig.CF_BASE_URL}/offerJudge")
                    .addHeader("X-API-Key", BuildConfig.CF_API_KEY)
                    .addHeader("Content-Type", "application/json")
                    .post(body.toString().toRequestBody("application/json".toMediaType()))
                    .build()

                val response = client.newCall(request).execute()
                val responseBody = response.body?.string() ?: return@withContext null

                if (!response.isSuccessful) {
                    Log.e(TAG, "CF error: ${response.code} $responseBody")
                    return@withContext null
                }

                parseJudgment(responseBody, offer)
            } catch (e: Exception) {
                Log.e(TAG, "Judge request failed", e)
                null
            }
        }
    }

    private fun parseJudgment(responseBody: String, offer: KittAccessibilityService.OfferData): JudgmentResult {
        val json = Json.parseToJsonElement(responseBody).jsonObject

        return JudgmentResult(
            app = offer.app,
            decision = json["decision"]?.jsonPrimitive?.content ?: "unknown",
            reward = offer.reward ?: 0,
            estimatedHourlyRate = json["estimatedHourlyRate"]?.jsonPrimitive?.intOrNull ?: 0,
            effectiveHourlyRate = json["effectiveHourlyRate"]?.jsonPrimitive?.intOrNull ?: 0,
            storeName = offer.storeName ?: "不明",
            reason = json["reason"]?.jsonPrimitive?.content ?: "",
            score = json["score"]?.jsonPrimitive?.doubleOrNull ?: 0.0,
            threshold = json["threshold"]?.jsonPrimitive?.doubleOrNull ?: 0.85
        )
    }

    data class JudgmentResult(
        val app: String,
        val decision: String,     // "accept" or "reject"
        val reward: Int,
        val estimatedHourlyRate: Int,
        val effectiveHourlyRate: Int,
        val storeName: String,
        val reason: String,
        val score: Double,
        val threshold: Double
    )
}
