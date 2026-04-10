package com.kitt.app.service

import android.util.Log
import kotlinx.coroutines.*
import kotlinx.serialization.json.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import com.kitt.app.BuildConfig
import java.util.UUID
import java.util.concurrent.TimeUnit

/**
 * 配達の全ライフサイクルを状態機械として管理
 *
 * IDLE → OFFER_DETECTED → ACCEPTED → PICKING → AT_PICKUP → DELIVERING → DROPPED → IDLE
 *
 * 各ステップ遷移時にBQ delivery_trackingにGPS+タイムスタンプを記録
 */
class DeliveryStateTracker {

    enum class State {
        IDLE,
        OFFER_DETECTED,
        OFFER_JUDGING,
        OFFER_REPORTED,
        ACCEPTED,
        PICKING,
        AT_PICKUP,
        DELIVERING,
        DROPPED
    }

    companion object {
        private const val TAG = "DeliveryTracker"
    }

    var currentState = State.IDLE
        private set
    var trackingId: String? = null
        private set
    var currentApp: String? = null
        private set
    var currentStoreName: String? = null
        private set
    var currentReward: Int? = null
        private set
    var currentDropoffAddress: String? = null
        private set

    private var lastStepTimestamp: Long = 0
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    private val client = OkHttpClient.Builder()
        .connectTimeout(5, TimeUnit.SECONDS)
        .readTimeout(10, TimeUnit.SECONDS)
        .build()

    // GPS注入用
    var locationProvider: LocationProvider? = null

    fun transition(newState: State, extras: Map<String, String> = emptyMap()) {
        val oldState = currentState
        currentState = newState
        Log.d(TAG, "State: $oldState → $newState")

        when (newState) {
            State.OFFER_DETECTED -> {
                trackingId = "trk_${UUID.randomUUID().toString().take(8)}"
                currentApp = extras["app"]
                currentStoreName = extras["storeName"]
                currentReward = extras["reward"]?.toIntOrNull()
                currentDropoffAddress = extras["dropoffAddress"]
                lastStepTimestamp = System.currentTimeMillis()
                postStep("offer_detected")
            }
            State.OFFER_JUDGING -> {
                // CF判定送信中（ログのみ）
            }
            State.OFFER_REPORTED -> {
                // Shujiの判断待ち
            }
            State.ACCEPTED -> {
                postStep("accepted")
            }
            State.PICKING -> {
                postStep("picking")
            }
            State.AT_PICKUP -> {
                postStep("at_pickup")
            }
            State.DELIVERING -> {
                postStep("delivering")
            }
            State.DROPPED -> {
                postStep("dropped")
                // 配達完了 → IDLEにリセット
                scope.launch {
                    delay(5000) // 5秒後にリセット（リザルト画面の読取時間）
                    reset()
                }
            }
            State.IDLE -> {
                // 何もしない
            }
        }
    }

    fun reset() {
        currentState = State.IDLE
        trackingId = null
        currentApp = null
        currentStoreName = null
        currentReward = null
        currentDropoffAddress = null
        lastStepTimestamp = 0
        Log.d(TAG, "Reset to IDLE")
    }

    private fun postStep(step: String) {
        val now = System.currentTimeMillis()
        scope.launch {
            try {
                val body = buildJsonObject {
                    put("tracking_id", trackingId)
                    put("step", step)
                    put("app", currentApp ?: "")
                    put("store_name", currentStoreName ?: "")
                    put("dropoff_address", currentDropoffAddress ?: "")
                    currentReward?.let { put("reward", it) }
                    locationProvider?.lat?.let { put("lat", it) }
                    locationProvider?.lng?.let { put("lng", it) }
                    if (lastStepTimestamp > 0) {
                        put("prev_step_timestamp", java.text.SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'", java.util.Locale.US).apply {
                            timeZone = java.util.TimeZone.getTimeZone("UTC")
                        }.format(java.util.Date(lastStepTimestamp)))
                    }
                }
                lastStepTimestamp = now

                val request = Request.Builder()
                    .url("${BuildConfig.CF_BASE_URL}/deliveryTrack")
                    .addHeader("X-API-Key", BuildConfig.CF_API_KEY)
                    .addHeader("Content-Type", "application/json")
                    .post(body.toString().toRequestBody("application/json".toMediaType()))
                    .build()

                val response = client.newCall(request).execute()
                val responseBody = response.body?.string()
                Log.d(TAG, "deliveryTrack $step: ${response.code} $responseBody")
            } catch (e: Exception) {
                Log.e(TAG, "deliveryTrack $step failed", e)
            }
        }
    }

    fun destroy() {
        scope.cancel()
    }
}
