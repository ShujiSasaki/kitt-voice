package com.kitt.app.service

import android.annotation.SuppressLint
import android.content.Context
import android.location.Location
import android.os.Looper
import android.util.Log
import com.google.android.gms.location.*

/**
 * GPS位置情報を継続的に取得
 * FusedLocationProviderClient使用（Google Play Services）
 */
class LocationProvider(context: Context) {

    companion object {
        private const val TAG = "LocationProvider"
        private const val INTERVAL_MS = 10_000L       // 10秒間隔
        private const val FASTEST_INTERVAL_MS = 5_000L // 最短5秒
    }

    private val fusedClient = LocationServices.getFusedLocationProviderClient(context)
    private var currentLocation: Location? = null
    private var isTracking = false

    private val locationCallback = object : LocationCallback() {
        override fun onLocationResult(result: LocationResult) {
            result.lastLocation?.let {
                currentLocation = it
                Log.d(TAG, "Location: ${it.latitude}, ${it.longitude} (acc=${it.accuracy}m)")
            }
        }
    }

    val lat: Double? get() = currentLocation?.latitude
    val lng: Double? get() = currentLocation?.longitude
    val accuracy: Float? get() = currentLocation?.accuracy

    @SuppressLint("MissingPermission")
    fun startTracking() {
        if (isTracking) return

        val request = LocationRequest.Builder(Priority.PRIORITY_HIGH_ACCURACY, INTERVAL_MS)
            .setMinUpdateIntervalMillis(FASTEST_INTERVAL_MS)
            .setWaitForAccurateLocation(false)
            .build()

        fusedClient.requestLocationUpdates(request, locationCallback, Looper.getMainLooper())
        isTracking = true
        Log.d(TAG, "Location tracking started")

        // 即座に最後の位置を取得
        fusedClient.lastLocation.addOnSuccessListener { location ->
            if (location != null) {
                currentLocation = location
                Log.d(TAG, "Last known: ${location.latitude}, ${location.longitude}")
            }
        }
    }

    fun stopTracking() {
        if (!isTracking) return
        fusedClient.removeLocationUpdates(locationCallback)
        isTracking = false
        Log.d(TAG, "Location tracking stopped")
    }
}
