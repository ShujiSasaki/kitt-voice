package com.kitt.app

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager

class KittApplication : Application() {

    companion object {
        const val CHANNEL_KITT_SERVICE = "kitt_service"
        const val CHANNEL_KITT_OFFER = "kitt_offer"
        lateinit var instance: KittApplication
            private set
    }

    override fun onCreate() {
        super.onCreate()
        instance = this
        createNotificationChannels()
    }

    private fun createNotificationChannels() {
        val manager = getSystemService(NotificationManager::class.java)

        // KITT常駐サービス用 (サイレント)
        val serviceChannel = NotificationChannel(
            CHANNEL_KITT_SERVICE,
            "KITT Service",
            NotificationManager.IMPORTANCE_LOW
        ).apply {
            description = "KITTバックグラウンド稼働"
            setShowBadge(false)
        }

        // オファー判定通知用 (音あり)
        val offerChannel = NotificationChannel(
            CHANNEL_KITT_OFFER,
            "オファー判定",
            NotificationManager.IMPORTANCE_HIGH
        ).apply {
            description = "配達オファーの判定結果"
        }

        manager.createNotificationChannels(listOf(serviceChannel, offerChannel))
    }
}
