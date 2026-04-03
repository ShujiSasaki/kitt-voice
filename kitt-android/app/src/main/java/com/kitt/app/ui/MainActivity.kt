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
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import com.kitt.app.service.KittForegroundService

class MainActivity : ComponentActivity() {

    private val requiredPermissions = arrayOf(
        Manifest.permission.RECORD_AUDIO,
        Manifest.permission.ACCESS_FINE_LOCATION,
        Manifest.permission.ACCESS_COARSE_LOCATION,
        Manifest.permission.BLUETOOTH_CONNECT,
        Manifest.permission.POST_NOTIFICATIONS
    )

    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { permissions ->
        if (permissions.values.all { it }) {
            startKittService()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        setContent {
            KittTheme {
                KittScreen()
            }
        }

        // 権限チェック → サービス開始
        if (hasAllPermissions()) {
            startKittService()
        } else {
            permissionLauncher.launch(requiredPermissions)
        }
    }

    private fun hasAllPermissions(): Boolean {
        return requiredPermissions.all {
            ContextCompat.checkSelfPermission(this, it) == PackageManager.PERMISSION_GRANTED
        }
    }

    private fun startKittService() {
        val intent = Intent(this, KittForegroundService::class.java)
        startForegroundService(intent)
    }

    @Composable
    fun KittScreen() {
        var isConnected by remember { mutableStateOf(false) }
        var statusText by remember { mutableStateOf("起動中...") }

        // サービス状態を監視
        LaunchedEffect(Unit) {
            kotlinx.coroutines.delay(2000)
            isConnected = KittForegroundService.instance?.geminiClient != null
            statusText = if (isConnected) "接続中" else "未接続"
        }

        Column(
            modifier = Modifier
                .fillMaxSize()
                .background(Color(0xFF0A0A0A))
                .padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center
        ) {
            // KITTロゴ
            Text(
                text = "KITT",
                fontSize = 48.sp,
                fontWeight = FontWeight.Black,
                color = Color(0xFFE03030),
                letterSpacing = 12.sp
            )

            Spacer(modifier = Modifier.height(8.dp))

            Text(
                text = "AI DELIVERY AGENT",
                fontSize = 10.sp,
                color = Color(0xFF666666),
                letterSpacing = 4.sp
            )

            Spacer(modifier = Modifier.height(48.dp))

            // ステータスインジケーター
            Box(
                modifier = Modifier
                    .size(80.dp)
                    .background(
                        color = if (isConnected) Color(0xFF30D060).copy(alpha = 0.1f)
                        else Color(0xFFE03030).copy(alpha = 0.1f),
                        shape = CircleShape
                    ),
                contentAlignment = Alignment.Center
            ) {
                Box(
                    modifier = Modifier
                        .size(16.dp)
                        .background(
                            color = if (isConnected) Color(0xFF30D060) else Color(0xFFE03030),
                            shape = CircleShape
                        )
                )
            }

            Spacer(modifier = Modifier.height(16.dp))

            Text(
                text = statusText,
                fontSize = 14.sp,
                color = if (isConnected) Color(0xFF30D060) else Color(0xFF666666)
            )

            Spacer(modifier = Modifier.height(48.dp))

            // 設定ボタン群
            Column(
                modifier = Modifier.fillMaxWidth(),
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                // 通知アクセス設定
                OutlinedButton(
                    onClick = {
                        startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS))
                    },
                    modifier = Modifier.fillMaxWidth(),
                    colors = ButtonDefaults.outlinedButtonColors(
                        contentColor = Color(0xFFE8E8E8)
                    )
                ) {
                    Text("通知アクセスを設定", fontSize = 12.sp)
                }

                // アクセシビリティ設定
                OutlinedButton(
                    onClick = {
                        startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
                    },
                    modifier = Modifier.fillMaxWidth(),
                    colors = ButtonDefaults.outlinedButtonColors(
                        contentColor = Color(0xFFE8E8E8)
                    )
                ) {
                    Text("アクセシビリティを設定", fontSize = 12.sp)
                }
            }

            Spacer(modifier = Modifier.weight(1f))

            Text(
                text = "v1.0.0",
                fontSize = 10.sp,
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
