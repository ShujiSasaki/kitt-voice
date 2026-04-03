package com.kitt.app.audio

import android.annotation.SuppressLint
import android.content.Context
import android.media.*
import android.util.Log
import kotlinx.coroutines.*

/**
 * Bluetoothオーディオルーティング + AudioFocus管理
 *
 * - DJI MIC MINI (BT) → 音声入力 (16kHz PCM16)
 * - AirPods Pro 2 (BT) → 音声出力 (24kHz PCM16)
 * - AudioFocus: KITTが喋るときメディア音量ダック → 終わったら復帰
 */
class AudioRouter(private val context: Context) {

    private val audioManager = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager
    private var audioRecord: AudioRecord? = null
    private var audioTrack: AudioTrack? = null
    private var micJob: Job? = null
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    private var hasAudioFocus = false

    companion object {
        private const val TAG = "AudioRouter"
        private const val MIC_SAMPLE_RATE = 16000  // Gemini入力用
        private const val PLAY_SAMPLE_RATE = 24000  // Gemini出力用
        private const val MIC_BUFFER_SIZE = 1600     // 100msのPCM16データ (16000 * 0.1 * 2bytes / 2)
    }

    // AudioFocusリスナー
    private val focusChangeListener = AudioManager.OnAudioFocusChangeListener { focusChange ->
        when (focusChange) {
            AudioManager.AUDIOFOCUS_GAIN -> {
                Log.d(TAG, "AudioFocus gained")
            }
            AudioManager.AUDIOFOCUS_LOSS,
            AudioManager.AUDIOFOCUS_LOSS_TRANSIENT -> {
                Log.d(TAG, "AudioFocus lost")
                hasAudioFocus = false
            }
        }
    }

    /**
     * マイクキャプチャ開始 (DJI MIC MINI → PCM16)
     */
    @SuppressLint("MissingPermission")
    fun startMicCapture(onAudioData: (ByteArray) -> Unit) {
        if (audioRecord != null) return

        val bufferSize = AudioRecord.getMinBufferSize(
            MIC_SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT
        )

        audioRecord = AudioRecord(
            MediaRecorder.AudioSource.VOICE_COMMUNICATION, // BT SCO対応
            MIC_SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
            bufferSize
        )

        // Bluetooth SCOを有効化 (BT マイクを使用)
        audioManager.apply {
            mode = AudioManager.MODE_IN_COMMUNICATION
            isBluetoothScoOn = true
            startBluetoothSco()
        }

        audioRecord?.startRecording()
        Log.d(TAG, "Mic capture started (${MIC_SAMPLE_RATE}Hz)")

        micJob = scope.launch {
            val buffer = ByteArray(MIC_BUFFER_SIZE)
            while (isActive) {
                val read = audioRecord?.read(buffer, 0, buffer.size) ?: -1
                if (read > 0) {
                    onAudioData(buffer.copyOf(read))
                }
            }
        }
    }

    /**
     * マイクキャプチャ停止
     */
    fun stopMicCapture() {
        micJob?.cancel()
        micJob = null
        audioRecord?.stop()
        audioRecord?.release()
        audioRecord = null

        audioManager.apply {
            stopBluetoothSco()
            isBluetoothScoOn = false
            mode = AudioManager.MODE_NORMAL
        }

        Log.d(TAG, "Mic capture stopped")
    }

    /**
     * 音声データ再生 (Geminiからの音声 → AirPods)
     */
    fun playAudio(pcmData: ByteArray) {
        if (audioTrack == null) {
            initAudioTrack()
        }
        audioTrack?.write(pcmData, 0, pcmData.size)
    }

    private fun initAudioTrack() {
        val bufferSize = AudioTrack.getMinBufferSize(
            PLAY_SAMPLE_RATE,
            AudioFormat.CHANNEL_OUT_MONO,
            AudioFormat.ENCODING_PCM_16BIT
        )

        audioTrack = AudioTrack.Builder()
            .setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_ASSISTANT) // アシスタント音声
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                    .build()
            )
            .setAudioFormat(
                AudioFormat.Builder()
                    .setSampleRate(PLAY_SAMPLE_RATE)
                    .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                    .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                    .build()
            )
            .setBufferSizeInBytes(bufferSize)
            .setTransferMode(AudioTrack.MODE_STREAM)
            .build()

        audioTrack?.play()
        Log.d(TAG, "AudioTrack initialized (${PLAY_SAMPLE_RATE}Hz)")
    }

    /**
     * KITTが喋るとき: AudioFocusを取得してメディア音量をダック
     */
    fun requestAudioFocusForSpeech() {
        if (hasAudioFocus) return

        val focusRequest = AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT_MAY_DUCK)
            .setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_ASSISTANT)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                    .build()
            )
            .setOnAudioFocusChangeListener(focusChangeListener)
            .build()

        val result = audioManager.requestAudioFocus(focusRequest)
        hasAudioFocus = result == AudioManager.AUDIOFOCUS_REQUEST_GRANTED
        Log.d(TAG, "AudioFocus request: ${if (hasAudioFocus) "granted" else "denied"}")
    }

    /**
     * KITTの発話終了: AudioFocus解放してメディア音量復帰
     */
    fun abandonAudioFocus() {
        if (!hasAudioFocus) return

        val focusRequest = AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT_MAY_DUCK)
            .setOnAudioFocusChangeListener(focusChangeListener)
            .build()

        audioManager.abandonAudioFocusRequest(focusRequest)
        hasAudioFocus = false
        Log.d(TAG, "AudioFocus released")
    }

    fun release() {
        stopMicCapture()
        audioTrack?.stop()
        audioTrack?.release()
        audioTrack = null
        abandonAudioFocus()
    }
}
