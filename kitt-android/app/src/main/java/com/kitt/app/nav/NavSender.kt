package com.kitt.app.nav

import android.util.Log
import com.kitt.app.BuildConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody

/**
 * iPhoneのKITT Navアプリにナビゲーション先を送信
 *
 * Firebase RTDBの /nav パスに書き込む。
 * iPhone側のアプリがこのパスをリアルタイム監視して、
 * ナビ先が更新されたらMapKitでターンバイターンナビを自動開始。
 */
class NavSender {

    private val client = OkHttpClient()

    companion object {
        private const val TAG = "NavSender"
        private const val RTDB_URL = BuildConfig.FIREBASE_RTDB_URL
    }

    /**
     * ナビゲーション先をiPhoneに送信
     *
     * @param lat 緯度
     * @param lng 経度
     * @param name 場所名 (店名 or 住所)
     * @param type "pick" = ピック先, "drop" = ドロップ先, "standby" = 待機エリア
     */
    suspend fun sendNavigation(lat: Double, lng: Double, name: String, type: String) {
        withContext(Dispatchers.IO) {
            try {
                val data = buildJsonObject {
                    putJsonObject("destination") {
                        put("lat", lat)
                        put("lng", lng)
                        put("name", name)
                    }
                    put("type", type)
                    put("timestamp", System.currentTimeMillis())
                }

                // Firebase RTDB REST API で書き込み
                val url = "$RTDB_URL/nav.json?auth=${getFirebaseSecret()}"
                val request = Request.Builder()
                    .url(url)
                    .put(data.toString().toRequestBody("application/json".toMediaType()))
                    .build()

                val response = client.newCall(request).execute()
                if (response.isSuccessful) {
                    Log.d(TAG, "Nav sent: $type → $name ($lat, $lng)")
                } else {
                    Log.e(TAG, "Nav send failed: ${response.code}")
                }
            } catch (e: Exception) {
                Log.e(TAG, "Nav send error", e)
            }
        }
    }

    /**
     * ナビをクリア (稼働終了時)
     */
    suspend fun clearNavigation() {
        withContext(Dispatchers.IO) {
            try {
                val url = "$RTDB_URL/nav.json?auth=${getFirebaseSecret()}"
                val request = Request.Builder()
                    .url(url)
                    .delete()
                    .build()
                client.newCall(request).execute()
                Log.d(TAG, "Nav cleared")
            } catch (e: Exception) {
                Log.e(TAG, "Nav clear error", e)
            }
        }
    }

    private fun getFirebaseSecret(): String {
        return BuildConfig.FIREBASE_DB_SECRET
    }
}
