package com.kitt.app.ui

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import com.kitt.app.service.KittAccessibilityService
import com.kitt.app.service.KittForegroundService
import com.kitt.app.service.KittNotificationListener
import com.kitt.app.service.LocationProvider
import kotlinx.coroutines.delay

class MainActivity : ComponentActivity() {

    companion object {
        val notificationLogs = mutableListOf<NotificationLog>()
    }

    data class NotificationLog(
        val time: String,
        val app: String,
        val title: String,
        val text: String,
        val pkg: String
    )

    private val requiredPermissions = arrayOf(
        Manifest.permission.RECORD_AUDIO,
        Manifest.permission.BLUETOOTH_CONNECT,
        Manifest.permission.POST_NOTIFICATIONS,
        Manifest.permission.ACCESS_FINE_LOCATION
    )

    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { results ->
        // FINE_LOCATIONが許可されたらBACKGROUND_LOCATIONを別途リクエスト
        if (results[Manifest.permission.ACCESS_FINE_LOCATION] == true) {
            requestBackgroundLocationIfNeeded()
        }
    }

    private val bgLocationLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { _ -> }

    private var locationProvider: LocationProvider? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        if (!hasAllPermissions()) {
            permissionLauncher.launch(requiredPermissions)
        } else {
            requestBackgroundLocationIfNeeded()
        }

        // GPS開始
        locationProvider = LocationProvider(this).also { it.startTracking() }

        setContent {
            KittTheme {
                KittDashboard()
            }
        }
    }

    override fun onDestroy() {
        locationProvider?.stopTracking()
        super.onDestroy()
    }

    private fun hasAllPermissions(): Boolean {
        return requiredPermissions.all {
            ContextCompat.checkSelfPermission(this, it) == PackageManager.PERMISSION_GRANTED
        }
    }

    private fun isNotificationListenerEnabled(): Boolean {
        val flat = Settings.Secure.getString(contentResolver, "enabled_notification_listeners")
        return flat?.contains("com.kitt.app") == true
    }

    private fun requestBackgroundLocationIfNeeded() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_BACKGROUND_LOCATION)
            != PackageManager.PERMISSION_GRANTED
        ) {
            bgLocationLauncher.launch(Manifest.permission.ACCESS_BACKGROUND_LOCATION)
        }
    }

    private fun isA11yEnabled(): Boolean {
        val flat = Settings.Secure.getString(contentResolver, "enabled_accessibility_services")
        return flat?.contains("com.kitt.app") == true
    }

    @Composable
    fun KittDashboard() {
        var logs by remember { mutableStateOf(listOf<NotificationLog>()) }
        var listenerEnabled by remember { mutableStateOf(false) }
        var a11yEnabled by remember { mutableStateOf(false) }
        var fgServiceRunning by remember { mutableStateOf(false) }
        var gpsLat by remember { mutableStateOf<Double?>(null) }
        var gpsLng by remember { mutableStateOf<Double?>(null) }
        var gpsAcc by remember { mutableStateOf<Float?>(null) }
        val listState = rememberLazyListState()

        // 1秒ごとに全状態を更新
        LaunchedEffect(Unit) {
            while (true) {
                logs = notificationLogs.toList().reversed()
                listenerEnabled = isNotificationListenerEnabled()
                a11yEnabled = isA11yEnabled()
                fgServiceRunning = KittForegroundService.instance != null

                // GPS: ForegroundService → 自前LocationProvider の順
                val fgLocation = KittForegroundService.instance?.offerJudgeClient?.locationProvider
                val locProvider = fgLocation ?: locationProvider
                gpsLat = locProvider?.lat
                gpsLng = locProvider?.lng
                gpsAcc = locProvider?.accuracy

                delay(1000)
            }
        }

        Column(
            modifier = Modifier
                .fillMaxSize()
                .background(Color(0xFF0A0A0A))
                .padding(16.dp)
        ) {
            // ヘッダー
            Text(
                text = "KITT",
                fontSize = 28.sp,
                fontWeight = FontWeight.Bold,
                color = Color(0xFFE03030)
            )

            Spacer(modifier = Modifier.height(8.dp))

            // === サービス状態 ===
            ServiceStatusRow("通知リスナー", listenerEnabled)
            ServiceStatusRow("A11yサービス", a11yEnabled)
            ServiceStatusRow("常駐サービス", fgServiceRunning)

            // 通知リスナーOFFなら設定ボタン
            if (!listenerEnabled) {
                Spacer(modifier = Modifier.height(4.dp))
                Button(
                    onClick = {
                        startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS))
                    },
                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFE03030)),
                    modifier = Modifier.height(32.dp),
                    contentPadding = PaddingValues(horizontal = 12.dp, vertical = 0.dp)
                ) {
                    Text("通知アクセスを許可", fontSize = 11.sp)
                }
            }

            // A11yサービスOFFなら設定ボタン
            if (!a11yEnabled) {
                Spacer(modifier = Modifier.height(4.dp))
                Button(
                    onClick = {
                        startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
                    },
                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFE03030)),
                    modifier = Modifier.height(32.dp),
                    contentPadding = PaddingValues(horizontal = 12.dp, vertical = 0.dp)
                ) {
                    Text("A11yサービスを許可", fontSize = 11.sp)
                }
            }

            // ForegroundService開始ボタン
            if (!fgServiceRunning) {
                Spacer(modifier = Modifier.height(4.dp))
                Button(
                    onClick = {
                        val intent = Intent(this@MainActivity, KittForegroundService::class.java)
                        startForegroundService(intent)
                    },
                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF30D060)),
                    modifier = Modifier.height(32.dp),
                    contentPadding = PaddingValues(horizontal = 12.dp, vertical = 0.dp)
                ) {
                    Text("KITT起動", fontSize = 11.sp, color = Color.Black)
                }
            }

            Spacer(modifier = Modifier.height(8.dp))

            // === GPS ===
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("GPS: ", fontSize = 11.sp, color = Color(0xFF888888))
                if (gpsLat != null && gpsLng != null) {
                    Text(
                        String.format("%.5f, %.5f", gpsLat, gpsLng),
                        fontSize = 11.sp,
                        color = Color(0xFF30D060)
                    )
                    gpsAcc?.let {
                        Text(
                            " (${String.format("%.0f", it)}m)",
                            fontSize = 10.sp,
                            color = Color(0xFF666666)
                        )
                    }
                } else {
                    Text("取得中...", fontSize = 11.sp, color = Color(0xFF666666))
                }
            }

            // === 対象アプリ・CF判定 ===
            Spacer(modifier = Modifier.height(4.dp))
            Text(
                "対象: Uber / 出前館 / menu / ロケットナウ",
                fontSize = 10.sp, color = Color(0xFF666666)
            )
            Text(
                "CF判定: ${if (com.kitt.app.BuildConfig.CF_API_KEY.isNotEmpty()) "設定済み" else "未設定"}",
                fontSize = 10.sp,
                color = if (com.kitt.app.BuildConfig.CF_API_KEY.isNotEmpty()) Color(0xFF30D060) else Color(0xFFE03030)
            )

            Spacer(modifier = Modifier.height(8.dp))
            HorizontalDivider(color = Color(0xFF333333), thickness = 1.dp)
            Spacer(modifier = Modifier.height(8.dp))

            // === ログヘッダー ===
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "ログ: ${logs.size}件",
                    fontSize = 13.sp,
                    color = Color(0xFFCCCCCC)
                )
                OutlinedButton(
                    onClick = {
                        notificationLogs.clear()
                        logs = emptyList()
                    },
                    colors = ButtonDefaults.outlinedButtonColors(contentColor = Color(0xFF888888)),
                    modifier = Modifier.height(28.dp),
                    contentPadding = PaddingValues(horizontal = 10.dp, vertical = 0.dp)
                ) {
                    Text("クリア", fontSize = 10.sp)
                }
            }

            Spacer(modifier = Modifier.height(4.dp))

            // === 通知ログ一覧 ===
            LazyColumn(
                state = listState,
                modifier = Modifier.fillMaxSize()
            ) {
                items(logs) { log ->
                    NotificationItem(log)
                    HorizontalDivider(color = Color(0xFF222222), thickness = 0.5.dp)
                }
            }
        }
    }

    @Composable
    fun ServiceStatusRow(label: String, enabled: Boolean) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier.padding(vertical = 2.dp)
        ) {
            Box(
                modifier = Modifier
                    .size(8.dp)
                    .background(
                        if (enabled) Color(0xFF30D060) else Color(0xFFE03030),
                        shape = CircleShape
                    )
            )
            Spacer(modifier = Modifier.width(6.dp))
            Text(
                text = "$label: ${if (enabled) "ON" else "OFF"}",
                fontSize = 12.sp,
                color = if (enabled) Color(0xFF30D060) else Color(0xFFE03030)
            )
        }
    }

    @Composable
    fun NotificationItem(log: NotificationLog) {
        val isDelivery = log.pkg in KittNotificationListener.DELIVERY_APPS
        val isFinance = log.pkg in KittNotificationListener.FINANCE_APPS
        val isOffer = log.app.contains("オファー検知") || log.app.contains("判定結果")
        val isError = log.app.contains("エラー")

        val accentColor = when {
            isOffer && log.app.contains("✅") -> Color(0xFF30D060)
            isOffer && log.app.contains("❌") -> Color(0xFFE03030)
            isOffer -> Color(0xFFFFD700)
            isError -> Color(0xFFFF6B6B)
            isDelivery -> Color(0xFF30D060)
            isFinance -> Color(0xFFFFB74D)
            else -> Color(0xFF4FC3F7)
        }

        Column(modifier = Modifier.padding(vertical = 4.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Text(
                    text = log.app,
                    fontSize = 11.sp,
                    fontWeight = FontWeight.Bold,
                    color = accentColor,
                    modifier = Modifier.weight(1f)
                )
                Text(
                    text = log.time,
                    fontSize = 9.sp,
                    color = Color(0xFF555555)
                )
            }
            if (log.title.isNotEmpty()) {
                Text(
                    text = log.title,
                    fontSize = 11.sp,
                    color = Color(0xFFDDDDDD)
                )
            }
            if (log.text.isNotEmpty()) {
                Text(
                    text = log.text,
                    fontSize = 10.sp,
                    color = Color(0xFF999999),
                    maxLines = 20
                )
            }
            Text(
                text = log.pkg,
                fontSize = 8.sp,
                color = Color(0xFF333333)
            )
        }
    }
}

@Composable
fun KittTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = darkColorScheme(
            primary = Color(0xFFE03030),
            background = Color(0xFF0A0A0A),
            surface = Color(0xFF141414)
        ),
        content = content
    )
}
