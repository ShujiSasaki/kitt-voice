package com.kitt.app.service

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.AccessibilityServiceInfo
import android.util.Log
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import kotlinx.coroutines.*

/**
 * アプリのUI要素を直接読取り + 自動タップ
 *
 * 機能:
 * - 4社アプリのオファー画面からデータ抽出 (OCR不要)
 * - 受諾/拒否ボタンの自動タップ
 * - メディアアプリの操作 (YouTube/TVer/radiko/J:COM)
 * - カードアプリの利用額読取
 * - OMRON connectの測定データ読取
 */
class KittAccessibilityService : AccessibilityService() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    companion object {
        private const val TAG = "KittA11y"
        var instance: KittAccessibilityService? = null
            private set
    }

    override fun onServiceConnected() {
        super.onServiceConnected()
        instance = this

        serviceInfo = serviceInfo.apply {
            eventTypes = AccessibilityEvent.TYPES_ALL_MASK
            feedbackType = AccessibilityServiceInfo.FEEDBACK_GENERIC
            flags = flags or
                    AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS or
                    AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS or
                    AccessibilityServiceInfo.FLAG_INCLUDE_NOT_IMPORTANT_VIEWS
            notificationTimeout = 100
        }

        Log.d(TAG, "AccessibilityService connected")
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent) {
        // ウィンドウ変更を監視 (アプリ画面の切り替えを検知)
        if (event.eventType == AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED) {
            val pkg = event.packageName?.toString() ?: return
            if (pkg in KittNotificationListener.DELIVERY_APPS) {
                Log.d(TAG, "Delivery app window: $pkg")
            }
        }
    }

    override fun onInterrupt() {
        Log.w(TAG, "AccessibilityService interrupted")
    }

    override fun onDestroy() {
        instance = null
        scope.cancel()
        super.onDestroy()
    }

    // ==========================================
    // オファー読取り
    // ==========================================

    /**
     * 配達アプリのオファー画面からデータを構造化して抽出
     */
    suspend fun readOfferDetails(packageName: String): OfferData? {
        return withContext(Dispatchers.Main) {
            val rootNode = rootInActiveWindow ?: return@withContext null

            try {
                when (packageName) {
                    KittNotificationListener.PKG_UBER_DRIVER -> readUberOffer(rootNode)
                    KittNotificationListener.PKG_DEMAECAN -> readDemaecanOffer(rootNode)
                    KittNotificationListener.PKG_ROCKETNOW -> readRocketNowOffer(rootNode)
                    KittNotificationListener.PKG_MENU -> readMenuOffer(rootNode)
                    else -> null
                }
            } catch (e: Exception) {
                Log.e(TAG, "Failed to read offer from $packageName", e)
                // フォールバック: スクリーンショット → Gemini Vision
                null
            } finally {
                rootNode.recycle()
            }
        }
    }

    /**
     * Uber Driverのオファー画面読取
     *
     * UI構造 (実機で要確認・調整):
     * - 報酬: "¥XXX" テキスト
     * - 距離: "X.X km" テキスト
     * - 時間: "XX 分" テキスト
     * - 店名: テキストビュー
     * - 住所: テキストビュー
     * - 受諾ボタン / 拒否ボタン
     */
    private fun readUberOffer(root: AccessibilityNodeInfo): OfferData? {
        val allText = collectAllText(root)
        Log.d(TAG, "Uber UI text: $allText")

        // TODO: 実機でUI要素のID/テキストパターンを特定して精密なパースに置き換え
        // 現在は全テキストからパターンマッチで抽出
        val reward = extractReward(allText)
        val distance = extractDistance(allText)
        val duration = extractDuration(allText)
        val storeName = extractStoreName(allText)

        if (reward == null) {
            Log.w(TAG, "Could not extract Uber offer data")
            return null
        }

        return OfferData(
            app = "uber",
            reward = reward,
            distance = distance,
            duration = duration,
            storeName = storeName,
            rawText = allText.joinToString("\n")
        ).also {
            Log.d(TAG, "Uber offer: $it")
            // オファー判定を実行
            scope.launch { processOffer(it) }
        }
    }

    private fun readDemaecanOffer(root: AccessibilityNodeInfo): OfferData? {
        val allText = collectAllText(root)
        Log.d(TAG, "Demaecan UI text: $allText")
        // TODO: 出前館のUI構造を実機で調査して実装
        return OfferData(app = "demaecan", rawText = allText.joinToString("\n"))
    }

    private fun readRocketNowOffer(root: AccessibilityNodeInfo): OfferData? {
        val allText = collectAllText(root)
        Log.d(TAG, "RocketNow UI text: $allText")
        // TODO: ロケットナウのUI構造を実機で調査して実装
        return OfferData(app = "rocketnow", rawText = allText.joinToString("\n"))
    }

    private fun readMenuOffer(root: AccessibilityNodeInfo): OfferData? {
        val allText = collectAllText(root)
        Log.d(TAG, "Menu UI text: $allText")
        // TODO: menuのUI構造を実機で調査して実装
        return OfferData(app = "menu", rawText = allText.joinToString("\n"))
    }

    // ==========================================
    // 自動タップ
    // ==========================================

    /**
     * 受諾ボタンをタップ
     */
    fun tapAcceptButton(packageName: String): Boolean {
        val root = rootInActiveWindow ?: return false
        try {
            // アプリごとの受諾ボタンを探す
            val acceptNode = when (packageName) {
                KittNotificationListener.PKG_UBER_DRIVER ->
                    findNodeByText(root, "承諾") ?: findNodeByText(root, "申込み")
                KittNotificationListener.PKG_DEMAECAN ->
                    findNodeByText(root, "受諾") ?: findNodeByText(root, "配達する")
                KittNotificationListener.PKG_ROCKETNOW ->
                    findNodeByText(root, "受諾") ?: findNodeByText(root, "配達を開始")
                KittNotificationListener.PKG_MENU ->
                    findNodeByText(root, "受諾") ?: findNodeByText(root, "配達する")
                else -> null
            }

            if (acceptNode != null) {
                val clicked = acceptNode.performAction(AccessibilityNodeInfo.ACTION_CLICK)
                Log.d(TAG, "Accept tap: $clicked")
                acceptNode.recycle()
                return clicked
            }
        } finally {
            root.recycle()
        }
        return false
    }

    /**
     * 拒否ボタンをタップ
     */
    fun tapRejectButton(packageName: String): Boolean {
        val root = rootInActiveWindow ?: return false
        try {
            val rejectNode = when (packageName) {
                KittNotificationListener.PKG_UBER_DRIVER ->
                    findNodeByText(root, "拒否") ?: findNodeByContentDesc(root, "閉じる")
                else ->
                    findNodeByText(root, "拒否") ?: findNodeByText(root, "スキップ")
            }

            if (rejectNode != null) {
                val clicked = rejectNode.performAction(AccessibilityNodeInfo.ACTION_CLICK)
                Log.d(TAG, "Reject tap: $clicked")
                rejectNode.recycle()
                return clicked
            }
        } finally {
            root.recycle()
        }
        return false
    }

    // ==========================================
    // メディア操作
    // ==========================================

    /**
     * メディアアプリを操作 (YouTube/TVer/radiko/J:COM Stream)
     */
    fun controlMedia(action: String, app: String? = null, query: String? = null): Boolean {
        // TODO: 各メディアアプリのAccessibilityServiceによる操作
        // - play/pause/stop/volume_up/volume_down
        // - 特定のコンテンツを検索・再生
        Log.d(TAG, "Media control: action=$action app=$app query=$query")
        return false
    }

    // ==========================================
    // ユーティリティ
    // ==========================================

    /**
     * 画面上の全テキストを再帰的に収集
     */
    private fun collectAllText(node: AccessibilityNodeInfo): List<String> {
        val texts = mutableListOf<String>()
        node.text?.let { texts.add(it.toString()) }
        node.contentDescription?.let { texts.add(it.toString()) }
        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            texts.addAll(collectAllText(child))
            child.recycle()
        }
        return texts
    }

    private fun findNodeByText(root: AccessibilityNodeInfo, text: String): AccessibilityNodeInfo? {
        val nodes = root.findAccessibilityNodeInfosByText(text)
        return nodes.firstOrNull { it.isClickable }
            ?: nodes.firstOrNull()
    }

    private fun findNodeByContentDesc(root: AccessibilityNodeInfo, desc: String): AccessibilityNodeInfo? {
        // 再帰的にcontentDescriptionで探索
        if (root.contentDescription?.toString()?.contains(desc) == true && root.isClickable) {
            return root
        }
        for (i in 0 until root.childCount) {
            val child = root.getChild(i) ?: continue
            val found = findNodeByContentDesc(child, desc)
            if (found != null) return found
            child.recycle()
        }
        return null
    }

    // ==========================================
    // テキストからのデータ抽出 (AccessibilityServiceフォールバック)
    // ==========================================

    private fun extractReward(texts: List<String>): Int? {
        for (t in texts) {
            // ¥1,234 or ·1,234 or 1234円
            val match = Regex("""[¥￥·•]?\s*([0-9,]+)\s*円?""").find(t)
            val amount = match?.groupValues?.get(1)?.replace(",", "")?.toIntOrNull()
            if (amount != null && amount in 100..9999) return amount
        }
        return null
    }

    private fun extractDistance(texts: List<String>): Double? {
        for (t in texts) {
            val match = Regex("""(\d+\.?\d*)\s*km""", RegexOption.IGNORE_CASE).find(t)
            return match?.groupValues?.get(1)?.toDoubleOrNull()
        }
        return null
    }

    private fun extractDuration(texts: List<String>): Int? {
        for (t in texts) {
            val match = Regex("""(?:合計|約)?\s*(\d+)\s*分""").find(t)
            return match?.groupValues?.get(1)?.toIntOrNull()
        }
        return null
    }

    private fun extractStoreName(texts: List<String>): String? {
        // 日本語の店名らしい文字列を探す (漢字・ひらがな・カタカナを含む)
        for (t in texts) {
            if (t.length in 2..40 && t.matches(Regex(".*[\\p{IsHan}\\p{IsHiragana}\\p{IsKatakana}].*"))) {
                // 報酬や距離でない、店名らしいテキスト
                if (!t.contains("km") && !t.contains("分") && !t.contains("¥") && !t.contains("円")) {
                    return t
                }
            }
        }
        return null
    }

    /**
     * オファーをCloud Functionsに送って判定
     */
    private suspend fun processOffer(offer: OfferData) {
        val service = KittForegroundService.instance ?: return
        val result = service.offerJudgeClient.judge(offer)
        if (result != null) {
            service.handleOfferJudgment(result, offer.app)
        }
    }

    /**
     * オファーデータ
     */
    data class OfferData(
        val app: String,
        val reward: Int? = null,
        val distance: Double? = null,
        val duration: Int? = null,
        val storeName: String? = null,
        val dropoffAddress: String? = null,
        val rawText: String = ""
    )
}
