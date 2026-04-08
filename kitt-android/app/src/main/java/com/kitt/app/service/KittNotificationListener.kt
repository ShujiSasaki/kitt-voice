package com.kitt.app.service

import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import android.util.Log
import com.kitt.app.ui.MainActivity
import kotlinx.coroutines.*
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * 全アプリの通知を監視
 *
 * 対象:
 * - Uber Driver: 配達リクエスト
 * - 出前館 Driver: 配達リクエスト
 * - ロケットナウ: 配達リクエスト
 * - menu Driver: 配達リクエスト
 * - 三井住友銀行/VISA/JCB/PayPayカード: 利用通知・請求確定
 * - OMRON connect: 測定完了通知
 * - TimeTree: リマインダー
 */
class KittNotificationListener : NotificationListenerService() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    companion object {
        private const val TAG = "KittNotification"

        // 配達アプリのパッケージ名
        const val PKG_UBER_DRIVER = "com.ubercab.driver"
        const val PKG_DEMAECAN = "com.demaecan.DemaecanDriver"
        const val PKG_ROCKETNOW = "com.cpone.delivery"
        const val PKG_MENU = "inc.menu.deliverer"

        // カード・銀行アプリ
        const val PKG_SMBC = "jp.co.smbc.direct"
        const val PKG_SMBC_CARD = "jp.co.smbc.card.vpass"
        const val PKG_JCB = "com.jcb.myJCB"
        const val PKG_PAYPAY_CARD = "jp.ne.paypay.android.app" // PayPayアプリ内カード

        // ヘルスケア
        const val PKG_OMRON = "jp.co.omron.healthcare.omron_connect"

        // カレンダー
        const val PKG_TIMETREE = "com.timetreeapp.timetree"

        // 配達アプリ一覧
        val DELIVERY_APPS = setOf(PKG_UBER_DRIVER, PKG_DEMAECAN, PKG_ROCKETNOW, PKG_MENU)
        // カード・銀行アプリ一覧
        val FINANCE_APPS = setOf(PKG_SMBC, PKG_SMBC_CARD, PKG_JCB, PKG_PAYPAY_CARD)

        var instance: KittNotificationListener? = null
            private set
    }

    override fun onCreate() {
        super.onCreate()
        instance = this
        Log.d(TAG, "NotificationListener started")
    }

    override fun onDestroy() {
        instance = null
        scope.cancel()
        super.onDestroy()
    }

    override fun onNotificationPosted(sbn: StatusBarNotification) {
        val pkg = sbn.packageName
        val extras = sbn.notification.extras
        val title = extras.getString("android.title") ?: ""
        val text = extras.getCharSequence("android.text")?.toString() ?: ""

        Log.d(TAG, "Notification: pkg=$pkg title=$title text=$text")

        // UIにログ追加
        val timeStr = SimpleDateFormat("HH:mm:ss", Locale.JAPAN).format(Date())
        val appName = when (pkg) {
            PKG_UBER_DRIVER -> "Uber Driver"
            PKG_DEMAECAN -> "出前館"
            PKG_ROCKETNOW -> "ロケットナウ"
            PKG_MENU -> "menu"
            else -> pkg.substringAfterLast(".")
        }
        MainActivity.notificationLogs.add(
            MainActivity.NotificationLog(timeStr, appName, title, text, pkg)
        )
        // 最大100件
        if (MainActivity.notificationLogs.size > 100) {
            MainActivity.notificationLogs.removeAt(0)
        }

        when {
            pkg in DELIVERY_APPS -> handleDeliveryNotification(pkg, title, text, sbn)
            pkg in FINANCE_APPS -> handleFinanceNotification(pkg, title, text)
            pkg == PKG_OMRON -> handleHealthNotification(title, text)
            pkg == PKG_TIMETREE -> handleCalendarNotification(title, text)
        }
    }

    override fun onNotificationRemoved(sbn: StatusBarNotification) {
        // 通知が消された = ユーザーが対応した or タイムアウト
    }

    /**
     * 配達アプリの通知 → AccessibilityServiceでオファー詳細を読む
     */
    private fun handleDeliveryNotification(
        pkg: String,
        title: String,
        text: String,
        sbn: StatusBarNotification
    ) {
        val appName = when (pkg) {
            PKG_UBER_DRIVER -> "Uber"
            PKG_DEMAECAN -> "出前館"
            PKG_ROCKETNOW -> "ロケットナウ"
            PKG_MENU -> "menu"
            else -> "unknown"
        }
        Log.d(TAG, "🔔 $appName offer: $title / $text")

        scope.launch {
            // AccessibilityServiceにオファー読取を依頼
            KittAccessibilityService.instance?.readOfferDetails(pkg)
        }
    }

    /**
     * カード・銀行の通知 → 利用額・請求額を抽出
     */
    private fun handleFinanceNotification(pkg: String, title: String, text: String) {
        Log.d(TAG, "💰 Finance: $title / $text")

        // 金額パターン: ¥1,234 or 1,234円 or ￥1,234
        val amountRegex = Regex("""[¥￥]?\s*([0-9,]+)\s*円?""")
        val match = amountRegex.find(text)
        val amount = match?.groupValues?.get(1)?.replace(",", "")?.toIntOrNull()

        if (amount != null) {
            scope.launch {
                // KITTに金額を報告 + BQに記録 + TimeTreeに書き込み
                KittForegroundService.instance?.let { service ->
                    service.geminiClient.sendText(
                        "【カード利用通知】$title: ¥${amount}円"
                    )
                }
                // TODO: TimeTree APIで引き落とし予定に反映
                // TODO: BQに記録
            }
        }
    }

    /**
     * OMRON connect通知 → 体組成・血圧データ取得
     */
    private fun handleHealthNotification(title: String, text: String) {
        Log.d(TAG, "🏥 Health: $title / $text")

        scope.launch {
            // AccessibilityServiceでOMRON connectアプリからデータ読取
            // TODO: 体重・体脂肪率・血圧・脈拍を取得してBQに記録
        }
    }

    /**
     * TimeTree通知 → 予定リマインダーをKITTに伝える
     */
    private fun handleCalendarNotification(title: String, text: String) {
        Log.d(TAG, "📅 Calendar: $title / $text")

        scope.launch {
            KittForegroundService.instance?.geminiClient?.sendText(
                "【予定リマインダー】$title: $text"
            )
        }
    }
}
