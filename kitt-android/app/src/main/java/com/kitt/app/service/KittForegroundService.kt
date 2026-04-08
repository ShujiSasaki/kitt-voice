package com.kitt.app.service

import android.app.Notification
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.os.IBinder
import android.os.PowerManager
import androidx.core.app.NotificationCompat
import com.kitt.app.KittApplication
import com.kitt.app.R
import com.kitt.app.audio.AudioRouter
import com.kitt.app.audio.GeminiLiveAudioClient
import com.kitt.app.nav.NavSender
import com.kitt.app.offer.OfferJudgeClient
import com.kitt.app.ui.MainActivity
import kotlinx.coroutines.*

/**
 * KITT常駐サービス - アプリの心臓部
 *
 * Foreground Serviceとして永続稼働:
 * - Gemini Live Audio WebSocket接続維持
 * - BTオーディオルーティング (DJI MIC MINI入力 / AirPods出力)
 * - GPS継続取得
 * - オファー判定結果の音声出力
 * - AudioFocus管理 (メディアアプリとの共存)
 */
class KittForegroundService : Service() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    private var wakeLock: PowerManager.WakeLock? = null

    lateinit var audioRouter: AudioRouter
        private set
    lateinit var geminiClient: GeminiLiveAudioClient
        private set
    lateinit var offerJudgeClient: OfferJudgeClient
        private set
    lateinit var locationProvider: LocationProvider
        private set
    lateinit var navSender: NavSender
        private set

    companion object {
        var instance: KittForegroundService? = null
            private set
        private const val NOTIFICATION_ID = 1
    }

    override fun onCreate() {
        super.onCreate()
        instance = this

        audioRouter = AudioRouter(this)
        geminiClient = GeminiLiveAudioClient(audioRouter)
        locationProvider = LocationProvider(this).also { it.startTracking() }
        offerJudgeClient = OfferJudgeClient().also { it.locationProvider = locationProvider }
        navSender = NavSender()

        // WakeLock: CPU稼働維持 (画面OFFでも動作)
        val pm = getSystemService(PowerManager::class.java)
        wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "kitt:service").apply {
            acquire()
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        startForeground(NOTIFICATION_ID, buildNotification("KITT 稼働中"))
        scope.launch { geminiClient.connect() }
        return START_STICKY // OS に kill されても再起動
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        instance = null
        scope.cancel()
        geminiClient.disconnect()
        audioRouter.release()
        locationProvider.stopTracking()
        wakeLock?.let { if (it.isHeld) it.release() }
        super.onDestroy()
    }

    fun updateNotification(text: String) {
        val manager = getSystemService(android.app.NotificationManager::class.java)
        manager.notify(NOTIFICATION_ID, buildNotification(text))
    }

    /**
     * オファー判定結果を処理
     * - Gemini Live Audioで音声報告
     * - iPhoneにナビ先を送信 (受諾時)
     */
    fun handleOfferJudgment(
        judgment: OfferJudgeClient.JudgmentResult,
        offerApp: String
    ) {
        scope.launch {
            // AudioFocusを取得してメディア音量をダック
            audioRouter.requestAudioFocusForSpeech()

            // function callingで受諾/拒否するときにどのアプリか伝える
            geminiClient.setCurrentOfferApp(offerApp)
            geminiClient.setCurrentJudgment(judgment)

            // KITTが判定理由を音声で報告
            geminiClient.sendOfferContext(judgment)
        }
    }

    /**
     * オファー受諾後: iPhoneにピック先ナビを送信
     */
    fun onOfferAccepted(pickupLat: Double, pickupLng: Double, storeName: String) {
        scope.launch {
            navSender.sendNavigation(pickupLat, pickupLng, storeName, "pick")
            updateNotification("ピック中: $storeName")
        }
    }

    /**
     * ピック完了: iPhoneにドロップ先ナビを送信
     */
    fun onPickupComplete(dropLat: Double, dropLng: Double, dropAddress: String) {
        scope.launch {
            navSender.sendNavigation(dropLat, dropLng, dropAddress, "drop")
            updateNotification("ドロップ中: $dropAddress")
        }
    }

    /**
     * ドロップ完了: iPhoneに待機エリア or 帰宅方向ナビ
     */
    fun onDropoffComplete() {
        scope.launch {
            updateNotification("KITT 待機中")
            // AudioFocus解放 → メディア音量復帰
            audioRouter.abandonAudioFocus()
        }
    }

    private fun buildNotification(text: String): Notification {
        val intent = Intent(this, MainActivity::class.java)
        val pendingIntent = PendingIntent.getActivity(
            this, 0, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        return NotificationCompat.Builder(this, KittApplication.CHANNEL_KITT_SERVICE)
            .setContentTitle("KITT")
            .setContentText(text)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentIntent(pendingIntent)
            .setOngoing(true)
            .setSilent(true)
            .build()
    }
}
