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
import com.kitt.app.context.ContextBridgeClient
import com.kitt.app.context.ConversationLogger
import com.kitt.app.nav.NavSender
import com.kitt.app.offer.OfferJudgeClient
import com.kitt.app.ui.MainActivity
import kotlinx.coroutines.*

/**
 * KITT常駐サービス - アプリの心臓部
 *
 * Foreground Serviceとして永続稼働:
 * - Gemini Live Audio WebSocket接続維持
 * - BTオーディオルーティング (ピンマイク入力 / AirPods出力)
 * - GPS継続取得 (待機3秒 / 配達中1秒)
 * - オファー判定結果の音声出力
 * - 配達ステップ追跡 (DeliveryStateTracker)
 * - 会話ログ保存 (ConversationLogger)
 * - 文脈管理 (ContextBridgeClient)
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
    lateinit var deliveryTracker: DeliveryStateTracker
        private set
    lateinit var conversationLogger: ConversationLogger
        private set
    lateinit var contextBridge: ContextBridgeClient
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
        deliveryTracker = DeliveryStateTracker().also { it.locationProvider = locationProvider }
        conversationLogger = ConversationLogger().also { it.start() }
        contextBridge = ContextBridgeClient()

        // WakeLock: CPU稼働維持 (画面OFFでも動作)
        val pm = getSystemService(PowerManager::class.java)
        wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "kitt:service").apply {
            acquire()
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        startForeground(NOTIFICATION_ID, buildNotification("KITT 稼働中"))
        scope.launch {
            // 再接続時: BQから文脈を取得してシステムプロンプトに注入
            val context = contextBridge.fetchReconnectContext()
            geminiClient.setDynamicContext(context)
            geminiClient.connect()
        }
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        instance = null
        scope.cancel()
        geminiClient.disconnect()
        audioRouter.release()
        locationProvider.stopTracking()
        deliveryTracker.destroy()
        conversationLogger.destroy()
        wakeLock?.let { if (it.isHeld) it.release() }
        super.onDestroy()
    }

    fun updateNotification(text: String) {
        val manager = getSystemService(android.app.NotificationManager::class.java)
        manager.notify(NOTIFICATION_ID, buildNotification(text))
    }

    /**
     * オファー判定結果を処理
     */
    fun handleOfferJudgment(
        judgment: OfferJudgeClient.JudgmentResult,
        offerApp: String
    ) {
        scope.launch {
            audioRouter.requestAudioFocusForSpeech()
            geminiClient.setCurrentOfferApp(offerApp)
            geminiClient.setCurrentJudgment(judgment)
            geminiClient.sendOfferContext(judgment)

            // 会話ログに記録
            conversationLogger.logAssistant(
                "オファー判定: ${judgment.decision} ¥${judgment.reward} ${judgment.storeName}",
                offerContext = judgment.app
            )
        }
    }

    /**
     * オファー受諾後: iPhoneにピック先ナビを送信
     */
    fun onOfferAccepted(pickupLat: Double, pickupLng: Double, storeName: String) {
        scope.launch {
            navSender.sendNavigation(pickupLat, pickupLng, storeName, "pick")
            updateNotification("ピック中: $storeName")
            deliveryTracker.transition(DeliveryStateTracker.State.PICKING)
        }
    }

    /**
     * ピック完了: iPhoneにドロップ先ナビを送信
     */
    fun onPickupComplete(dropLat: Double, dropLng: Double, dropAddress: String) {
        scope.launch {
            navSender.sendNavigation(dropLat, dropLng, dropAddress, "drop")
            updateNotification("ドロップ中: $dropAddress")
            deliveryTracker.transition(DeliveryStateTracker.State.DELIVERING)
        }
    }

    /**
     * ドロップ完了
     */
    fun onDropoffComplete() {
        scope.launch {
            updateNotification("KITT 待機中")
            audioRouter.abandonAudioFocus()
            deliveryTracker.transition(DeliveryStateTracker.State.DROPPED)
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
