package com.kitt.app.service

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.AccessibilityServiceInfo
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Intent
import android.util.Log
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import androidx.core.app.NotificationCompat
import com.kitt.app.KittApplication
import com.kitt.app.R
import com.kitt.app.offer.OfferJudgeClient
import com.kitt.app.ui.MainActivity
import kotlinx.coroutines.*
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

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

    // 最後にダンプした時刻（連続ダンプ防止）
    private var lastDumpTime = 0L
    // 最後にCF判定を送った時刻（重複防止: NotificationListener経由とA11yイベント経由の二重送信防止）
    private var lastJudgeTime = 0L
    private val JUDGE_COOLDOWN_MS = 15_000L // 同一オファーの再判定を15秒ブロック

    override fun onAccessibilityEvent(event: AccessibilityEvent) {
        val pkg = event.packageName?.toString() ?: return

        // 配達アプリのウィンドウ変更・コンテンツ変更を監視
        if (pkg in KittNotificationListener.DELIVERY_APPS) {
            when (event.eventType) {
                AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED,
                AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED -> {
                    val now = System.currentTimeMillis()
                    // 2秒以内の連続ダンプは無視
                    if (now - lastDumpTime < 2000) return
                    lastDumpTime = now

                    dumpAllWindows(pkg)
                }
            }
        }
    }

    /**
     * 全ウィンドウ（オーバーレイ含む）をスキャンして配達アプリのUIを読む
     */
    private fun dumpAllWindows(triggerPkg: String) {
        val timeStr = SimpleDateFormat("HH:mm:ss", Locale.JAPAN).format(Date())
        val appName = when (triggerPkg) {
            KittNotificationListener.PKG_UBER_DRIVER -> "Uber Driver"
            KittNotificationListener.PKG_DEMAECAN -> "出前館"
            KittNotificationListener.PKG_ROCKETNOW -> "ロケットナウ"
            KittNotificationListener.PKG_MENU -> "menu"
            else -> triggerPkg
        }

        try {
            // 全ウィンドウを走査（オーバーレイを含む）
            val allWindows = windows
            val targetTexts = mutableListOf<String>()
            val targetTree = StringBuilder()

            for (window in allWindows) {
                val root = window.root ?: continue
                val windowPkg = root.packageName?.toString() ?: ""

                // 配達アプリのウィンドウのみダンプ
                if (windowPkg == triggerPkg) {
                    val texts = collectAllText(root)
                    val tree = dumpNodeTree(root, 0)
                    targetTexts.addAll(texts)
                    targetTree.append("--- Window type=${window.type} layer=${window.layer} ---\n")
                    targetTree.append(tree)
                }
                root.recycle()
            }

            if (targetTexts.isNotEmpty()) {
                // UIテキストをログに追加
                MainActivity.notificationLogs.add(
                    MainActivity.NotificationLog(
                        time = timeStr,
                        app = "[$appName] A11y",
                        title = "UI要素 ${targetTexts.size}個",
                        text = targetTexts.joinToString(" | "),
                        pkg = triggerPkg
                    )
                )

                // ツリー構造もログに追加
                MainActivity.notificationLogs.add(
                    MainActivity.NotificationLog(
                        time = timeStr,
                        app = "[$appName] Tree",
                        title = "UIツリー",
                        text = targetTree.toString(),
                        pkg = triggerPkg
                    )
                )

                if (MainActivity.notificationLogs.size > 200) {
                    repeat(50) { MainActivity.notificationLogs.removeAt(0) }
                }

                Log.d(TAG, "[$appName] texts=${targetTexts.size}: ${targetTexts.take(10)}")

                // オファー検知: アプリ別に受諾ボタンの有無で判定
                val joinedText = targetTexts.joinToString(" ")
                // 報酬額が含まれているか (¥320 等。「基本料金」「クエスト」は除外)
                val hasReward = (joinedText.contains("¥") || joinedText.contains("￥") ||
                    joinedText.contains("·") || joinedText.contains("円")) &&
                    !joinedText.contains("基本料金") && !joinedText.contains("クエストを選択")

                // 待機画面の除外キーワード
                val isStandbyScreen = joinedText.contains("オンラインにする") ||
                    joinedText.contains("オフラインです") ||
                    joinedText.contains("ブーストが発生") ||
                    (joinedText.contains("配達を開始する") && !joinedText.contains("受諾"))

                val isOffer = !isStandbyScreen && when (triggerPkg) {
                    KittNotificationListener.PKG_UBER_DRIVER ->
                        joinedText.contains("承諾") && hasReward
                    KittNotificationListener.PKG_DEMAECAN ->
                        (joinedText.contains("受諾") || joinedText.contains("配達する")) && hasReward
                    KittNotificationListener.PKG_MENU ->
                        joinedText.contains("受け付ける") && hasReward &&
                        !joinedText.contains("ブースト") // ブースト通知画面除外
                    KittNotificationListener.PKG_ROCKETNOW ->
                        joinedText.contains("受諾") && hasReward // 「配達を開始する」だけでは反応しない
                    else -> false
                }

                if (isOffer) {
                    Log.d(TAG, "🔔 OFFER DETECTED in $appName!")
                    MainActivity.notificationLogs.add(
                        MainActivity.NotificationLog(
                            time = timeStr,
                            app = "🔔 $appName オファー検知",
                            title = "受諾ボタン検出 → 判定開始",
                            text = targetTexts.filter { t ->
                                t.contains("¥") || t.contains("km") || t.contains("分") ||
                                t.contains("円") || t.contains("承諾") || t.contains("受諾") ||
                                t.contains("受け付ける") ||
                                t.matches(Regex(".*[\\p{IsHan}\\p{IsHiragana}\\p{IsKatakana}].*"))
                            }.joinToString(" | "),
                            pkg = triggerPkg
                        )
                    )

                    // オファー読取 → CF判定（重複防止）
                    val now2 = System.currentTimeMillis()
                    if (now2 - lastJudgeTime < JUDGE_COOLDOWN_MS) {
                        Log.d(TAG, "Judge cooldown, skipping (${now2 - lastJudgeTime}ms since last)")
                        return
                    }
                    lastJudgeTime = now2

                    scope.launch {
                        val offerData = when (triggerPkg) {
                            KittNotificationListener.PKG_UBER_DRIVER -> readUberOffer(targetTexts)
                            KittNotificationListener.PKG_DEMAECAN -> readDemaecanOffer(targetTexts)
                            KittNotificationListener.PKG_MENU -> readMenuOffer(targetTexts)
                            KittNotificationListener.PKG_ROCKETNOW -> readRocketNowOffer(targetTexts)
                            else -> null
                        }
                        if (offerData != null) {
                            processOffer(offerData)
                        }
                    }
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to dump windows for $triggerPkg", e)
        }
    }

    /**
     * UIノードツリーをテキストで可視化（デバッグ用）
     */
    private fun dumpNodeTree(node: AccessibilityNodeInfo, depth: Int): String {
        val sb = StringBuilder()
        val indent = "  ".repeat(depth)
        val className = node.className?.toString()?.substringAfterLast(".") ?: "?"
        val text = node.text?.toString() ?: ""
        val desc = node.contentDescription?.toString() ?: ""
        val viewId = node.viewIdResourceName ?: ""
        val clickable = if (node.isClickable) " [CLICK]" else ""

        val info = buildString {
            append("$indent$className")
            if (viewId.isNotEmpty()) append(" id=$viewId")
            if (text.isNotEmpty()) append(" text=\"$text\"")
            if (desc.isNotEmpty()) append(" desc=\"$desc\"")
            append(clickable)
        }
        sb.appendLine(info)

        // 深さ制限（無限再帰防止）
        if (depth < 15) {
            for (i in 0 until node.childCount) {
                val child = node.getChild(i) ?: continue
                sb.append(dumpNodeTree(child, depth + 1))
                child.recycle()
            }
        }
        return sb.toString()
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
     * NotificationListenerからの呼び出し用（全ウィンドウをスキャン）
     */
    suspend fun readOfferDetails(packageName: String): OfferData? {
        // 重複防止: A11yイベントで既にCF判定送信済みならスキップ
        val now = System.currentTimeMillis()
        if (now - lastJudgeTime < JUDGE_COOLDOWN_MS) {
            Log.d(TAG, "readOfferDetails: judge cooldown, skipping")
            return null
        }

        return withContext(Dispatchers.Main) {
            try {
                val allTexts = mutableListOf<String>()
                for (window in windows) {
                    val root = window.root ?: continue
                    if (root.packageName?.toString() == packageName) {
                        allTexts.addAll(collectAllText(root))
                    }
                    root.recycle()
                }
                if (allTexts.isEmpty()) return@withContext null

                val offer = when (packageName) {
                    KittNotificationListener.PKG_UBER_DRIVER -> readUberOffer(allTexts)
                    KittNotificationListener.PKG_DEMAECAN -> readDemaecanOffer(allTexts)
                    KittNotificationListener.PKG_ROCKETNOW -> readRocketNowOffer(allTexts)
                    KittNotificationListener.PKG_MENU -> readMenuOffer(allTexts)
                    else -> null
                }

                // NotificationListener経由でオファー検知 → CF判定
                if (offer != null) {
                    lastJudgeTime = System.currentTimeMillis()
                    processOffer(offer)
                }

                offer
            } catch (e: Exception) {
                Log.e(TAG, "Failed to read offer from $packageName", e)
                null
            }
        }
    }

    /**
     * Uber Driverのオファー画面読取
     * 実機確認済みテキスト例: "¥320", "合計 12分 (2.0 km)", "ローソン 福岡黒門", "西公園中央区福岡市", "承諾"
     */
    private fun readUberOffer(texts: List<String>): OfferData {
        val reward = extractReward(texts)
        val distance = extractDistance(texts)
        val duration = extractDuration(texts)
        val storeName = extractStoreName(texts)
        val dropoff = extractDropoffAddress(texts)

        Log.d(TAG, "Uber offer: reward=$reward dist=$distance dur=$duration store=$storeName drop=$dropoff")

        return OfferData(
            app = "uber",
            reward = reward,
            distance = distance,
            duration = duration,
            storeName = storeName,
            dropoffAddress = dropoff,
            rawText = texts.joinToString("\n")
        )
    }

    /**
     * 出前館のオファー画面読取
     * TODO: 実オファーでUI構造を確認して精密化
     */
    private fun readDemaecanOffer(texts: List<String>): OfferData {
        return OfferData(
            app = "demaecan",
            reward = extractReward(texts),
            distance = extractDistance(texts),
            duration = extractDuration(texts),
            storeName = extractStoreName(texts),
            rawText = texts.joinToString("\n")
        )
    }

    /**
     * menuのオファー画面読取
     * 確認済み: テキストが1文字ずつバラバラに分かれてる → 結合して読む
     */
    private fun readMenuOffer(texts: List<String>): OfferData {
        // menuはテキストがバラバラなので結合してからパース
        val joined = texts.joinToString("")
        val joinedTexts = listOf(joined) + texts
        return OfferData(
            app = "menu",
            reward = extractReward(joinedTexts),
            distance = extractDistance(joinedTexts),
            duration = extractDuration(joinedTexts),
            storeName = extractStoreName(texts),
            rawText = joined
        )
    }

    /**
     * ロケットナウのオファー画面読取
     * 確認済み: "配達を開始する➔", Flutterアプリ(FLAG_SECURE)
     * TODO: 実オファーでUI構造を確認して精密化
     */
    private fun readRocketNowOffer(texts: List<String>): OfferData {
        return OfferData(
            app = "rocketnow",
            reward = extractReward(texts),
            distance = extractDistance(texts),
            duration = extractDuration(texts),
            storeName = extractStoreName(texts),
            rawText = texts.joinToString("\n")
        )
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

    /**
     * 報酬額抽出 (CF OCRパーサーのノウハウ反映)
     * 優先順: ¥/￥ → 中点(·•) → XXX円 パターン
     * 0始まり(地図番号)スキップ、100-9999円の範囲制限
     */
    private fun extractReward(texts: List<String>): Int? {
        // Pass 1: ¥/￥ + 数字
        for (t in texts) {
            val match = Regex("""[¥￥]\s*([1-9][0-9,]{2,})""").find(t)
            val amount = match?.groupValues?.get(1)?.replace(",", "")?.toIntOrNull()
            if (amount != null && amount in 100..9999) return amount
        }
        // Pass 2: 中点パターン (iOS OCR互換: ¥→·変換)
        for (t in texts) {
            val match = Regex("""[·•]\s*([1-9][0-9,]{2,})""").find(t)
            val amount = match?.groupValues?.get(1)?.replace(",", "")?.toIntOrNull()
            if (amount != null && amount in 100..9999) return amount
        }
        // Pass 3: XXX円 (ロケットナウ形式)
        for (t in texts) {
            val match = Regex("""([1-9][0-9,]{2,})\s*円""").find(t)
            val amount = match?.groupValues?.get(1)?.replace(",", "")?.toIntOrNull()
            if (amount != null && amount in 100..9999) return amount
        }
        // Pass 4: +追加オファー (¥320+·200 等)
        for (t in texts) {
            val matches = Regex("""[¥￥·•]?\s*([1-9][0-9,]{2,})""").findAll(t)
            val total = matches.sumOf {
                it.groupValues[1].replace(",", "").toIntOrNull() ?: 0
            }
            if (total in 100..19999) return total
        }
        return null
    }

    /**
     * 距離抽出 (X.X km / 配達距離X.Xkm)
     */
    private fun extractDistance(texts: List<String>): Double? {
        // 「配達距離」を含む行を優先
        for (t in texts) {
            val match = Regex("""配達距離\s*(\d+\.?\d*)\s*km""", RegexOption.IGNORE_CASE).find(t)
            if (match != null) return match.groupValues[1].toDoubleOrNull()
        }
        // 一般的なkm表記
        for (t in texts) {
            val match = Regex("""(\d+\.?\d*)\s*km""", RegexOption.IGNORE_CASE).find(t)
            val dist = match?.groupValues?.get(1)?.toDoubleOrNull()
            if (dist != null && dist in 0.1..50.0) return dist
        }
        return null
    }

    /**
     * 所要時間抽出 (合計XX分 > 約XX分 > XX分)
     * バッテリー%の誤検知防止
     */
    private fun extractDuration(texts: List<String>): Int? {
        // 「合計XX分」を最優先
        for (t in texts) {
            val match = Regex("""合計\s*(\d+)\s*分""").find(t)
            if (match != null) return match.groupValues[1].toIntOrNull()
        }
        // 「約XX分」
        for (t in texts) {
            val match = Regex("""約\s*(\d+)\s*分""").find(t)
            if (match != null) return match.groupValues[1].toIntOrNull()
        }
        // 一般的な「XX分」（バッテリー%を除外: 数字の前に%があったらスキップ）
        for (t in texts) {
            if (t.contains("%")) continue // バッテリー表示除外
            val match = Regex("""(\d+)\s*分""").find(t)
            val min = match?.groupValues?.get(1)?.toIntOrNull()
            if (min != null && min in 1..120) return min
        }
        return null
    }

    /**
     * ドロップ先住所抽出
     * 区/市/町/丁目を含む、報酬等でないテキスト
     */
    private fun extractDropoffAddress(texts: List<String>): String? {
        val excludePatterns = setOf("km", "分", "¥", "￥", "承諾", "受諾", "拒否", "配達する", "受け付ける")
        for (t in texts) {
            if (t.length in 4..60 &&
                (t.contains("区") || t.contains("市") || t.contains("町") || t.contains("丁目")) &&
                excludePatterns.none { t.contains(it) }
            ) {
                return t
            }
        }
        return null
    }

    /**
     * 店名抽出 (CF OCRパーサーのノウハウ反映)
     * 「店屋亭堂」を含む行を優先、ゴミ除外強化
     */
    private fun extractStoreName(texts: List<String>): String? {
        val excludePatterns = setOf(
            "km", "分", "¥", "￥", "円", "承諾", "受諾", "拒否", "配達する",
            "受け付ける", "合計", "配達距離", "スキップ", "閉じる", "オンライン",
            "オフライン", "件のリクエスト"
        )
        val storeChars = Regex("[店屋亭堂館庵房苑]")

        // Pass 1: 「店屋亭堂」を含む行を優先
        for (t in texts) {
            if (t.length in 2..40 &&
                storeChars.containsMatchIn(t) &&
                t.matches(Regex(".*[\\p{IsHan}\\p{IsHiragana}\\p{IsKatakana}].*")) &&
                excludePatterns.none { t.contains(it) }
            ) {
                return t
            }
        }

        // Pass 2: 日本語の店名らしい文字列
        for (t in texts) {
            if (t.length in 2..40 &&
                t.matches(Regex(".*[\\p{IsHan}\\p{IsHiragana}\\p{IsKatakana}].*")) &&
                excludePatterns.none { t.contains(it) }
            ) {
                return t
            }
        }
        return null
    }

    /**
     * オファーをCloud Functionsに送って判定
     */
    private suspend fun processOffer(offer: OfferData) {
        val timeStr = SimpleDateFormat("HH:mm:ss", Locale.JAPAN).format(Date())

        // ForegroundServiceがあればそちら経由、なければ直接呼ぶ
        val judgeClient = KittForegroundService.instance?.offerJudgeClient
            ?: offerJudgeClientFallback

        try {
            val result = judgeClient.judge(offer)
            if (result != null) {
                // 判定結果をログに表示
                val emoji = if (result.decision == "accept") "✅" else "❌"
                MainActivity.notificationLogs.add(
                    MainActivity.NotificationLog(
                        time = timeStr,
                        app = "$emoji 判定結果",
                        title = "${result.decision.uppercase()} ¥${result.reward} ${result.storeName}",
                        text = "時給¥${result.estimatedHourlyRate} 実効¥${result.effectiveHourlyRate}\n" +
                               "スコア${String.format("%.2f", result.score)} (閾値${result.threshold})\n" +
                               result.reason,
                        pkg = offer.app
                    )
                )

                // Android通知バーに表示
                showJudgmentNotification(result)

                // ForegroundServiceがあれば音声報告も
                KittForegroundService.instance?.handleOfferJudgment(result, offer.app)
            } else {
                MainActivity.notificationLogs.add(
                    MainActivity.NotificationLog(
                        time = timeStr,
                        app = "⚠️ 判定エラー",
                        title = "CF応答なし",
                        text = "reward=${offer.reward} distance=${offer.distance} duration=${offer.duration}",
                        pkg = offer.app
                    )
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "processOffer failed", e)
            MainActivity.notificationLogs.add(
                MainActivity.NotificationLog(
                    time = timeStr,
                    app = "⚠️ 判定エラー",
                    title = e.message ?: "不明なエラー",
                    text = offer.rawText.take(200),
                    pkg = offer.app
                )
            )
        }
    }

    /**
     * 判定結果をAndroid通知バーに表示
     */
    private fun showJudgmentNotification(result: OfferJudgeClient.JudgmentResult) {
        val emoji = if (result.decision == "accept") "✅" else "❌"
        val title = "$emoji ${result.decision.uppercase()} ¥${result.reward} ${result.storeName}"
        val text = "時給¥${result.estimatedHourlyRate} 実効¥${result.effectiveHourlyRate}"

        val intent = Intent(this, MainActivity::class.java)
        val pendingIntent = PendingIntent.getActivity(
            this, 0, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val notification = NotificationCompat.Builder(this, KittApplication.CHANNEL_KITT_OFFER)
            .setContentTitle(title)
            .setContentText(text)
            .setStyle(NotificationCompat.BigTextStyle().bigText("$text\n${result.reason}"))
            .setSmallIcon(R.drawable.ic_notification)
            .setContentIntent(pendingIntent)
            .setAutoCancel(true)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .build()

        val manager = getSystemService(NotificationManager::class.java)
        manager.notify(System.currentTimeMillis().toInt(), notification)
    }

    // ForegroundService未起動時のフォールバック
    private val locationProvider by lazy {
        LocationProvider(applicationContext).also { it.startTracking() }
    }
    private val offerJudgeClientFallback by lazy {
        com.kitt.app.offer.OfferJudgeClient().also {
            it.locationProvider = locationProvider
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
