package com.pic2speech.app

import android.app.Activity
import android.content.Intent
import android.media.MediaPlayer
import android.media.PlaybackParams
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.View
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.SeekBar
import android.widget.Spinner
import android.widget.TextView
import android.widget.Toast
import androidx.core.content.FileProvider
import org.json.JSONObject
import java.io.File
import java.util.Locale

class MainActivity : Activity() {

    // ---------- 视图 ----------
    private lateinit var tvPick: TextView
    private lateinit var spLang: Spinner
    private lateinit var spVoice: Spinner
    private lateinit var spMode: Spinner
    private lateinit var spDetail: Spinner
    private lateinit var sbRate: SeekBar
    private lateinit var tvRate: TextView
    private lateinit var etKey: EditText
    private lateinit var tvKeyMsg: TextView
    private lateinit var btnGen: Button
    private lateinit var tvStatus: TextView
    private lateinit var etText: EditText
    private lateinit var btnResynth: Button
    private lateinit var btnPlay: Button
    private lateinit var btnShare: Button
    private lateinit var tvResult: TextView

    // ---------- 播放器面板 ----------
    private lateinit var playerBox: LinearLayout
    private lateinit var sbPos: SeekBar
    private lateinit var tvTime: TextView
    private lateinit var sbSpeed: SeekBar
    private lateinit var tvSpeed: TextView

    // ---------- 状态 ----------
    private val pickedUris = mutableListOf<Uri>()
    private var langs: List<Lang> = emptyList()
    private var lastMp3: String? = null
    private var player: MediaPlayer? = null

    /** 进度条刷新节拍器（主线程） */
    private val ui = Handler(Looper.getMainLooper())

    /** 用户正在拖动进度条：此时不要用播放位置去覆盖它 */
    private var userSeeking = false

    private val prefs by lazy { getSharedPreferences("pic2speech", MODE_PRIVATE) }

    companion object {
        private const val REQ_PICK = 1001
        private const val MAX_IMAGES = 8
        private const val TICK_MS = 250L
        private const val JUMP_MS = 5_000

        private val MODE_LABELS = listOf("看图解说", "朗读图中文字", "翻译朗读")
        private val MODE_CODES = listOf("talk", "read", "trans")
        private val DETAIL_LABELS = listOf("简洁", "标准", "详细")
        private val DETAIL_CODES = listOf("short", "standard", "long")

        /** 倍速档位：0.5x ~ 2.0x，每档 +0.1（共 16 档，第 5 档 = 1.0x） */
        private const val SPEED_MIN = 0.5f
        private const val SPEED_STEP = 0.1f
        private const val SPEED_STEPS = 16
    }

    private data class Voice(val id: String, val nick: String, val gender: String)
    private data class Lang(
        val code: String,
        val label: String,
        val promptName: String,
        val voices: List<Voice>
    )

    // =========================================================================
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        bindViews()
        setupStaticSpinners()
        setupRate()
        setupPlayer()
        wireButtons()
        restoreKey()
        restoreLastAudio()
        loadVoicesFromPython()
    }

    override fun onDestroy() {
        ui.removeCallbacksAndMessages(null)
        releasePlayer()
        super.onDestroy()
    }

    private fun bindViews() {
        tvPick = findViewById(R.id.tvPick)
        spLang = findViewById(R.id.spLang)
        spVoice = findViewById(R.id.spVoice)
        spMode = findViewById(R.id.spMode)
        spDetail = findViewById(R.id.spDetail)
        sbRate = findViewById(R.id.sbRate)
        tvRate = findViewById(R.id.tvRate)
        etKey = findViewById(R.id.etKey)
        tvKeyMsg = findViewById(R.id.tvKeyMsg)
        btnGen = findViewById(R.id.btnGen)
        tvStatus = findViewById(R.id.tvStatus)
        etText = findViewById(R.id.etText)
        btnResynth = findViewById(R.id.btnResynth)
        btnPlay = findViewById(R.id.btnPlay)
        btnShare = findViewById(R.id.btnShare)
        tvResult = findViewById(R.id.tvResult)

        playerBox = findViewById(R.id.playerBox)
        sbPos = findViewById(R.id.sbPos)
        tvTime = findViewById(R.id.tvTime)
        sbSpeed = findViewById(R.id.sbSpeed)
        tvSpeed = findViewById(R.id.tvSpeed)
    }

    private fun setupStaticSpinners() {
        spMode.adapter = spinnerAdapter(MODE_LABELS)
        spDetail.adapter = spinnerAdapter(DETAIL_LABELS)
        spDetail.setSelection(1) // 默认“标准”
    }

    private fun spinnerAdapter(items: List<String>) =
        ArrayAdapter(this, android.R.layout.simple_spinner_item, items).apply {
            setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        }

    private fun setupRate() {
        tvRate.text = "0%"
        sbRate.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(seekBar: SeekBar?, progress: Int, fromUser: Boolean) {
                tvRate.text = "${progress - 30}%"
            }

            override fun onStartTrackingTouch(seekBar: SeekBar?) {}
            override fun onStopTrackingTouch(seekBar: SeekBar?) {}
        })
    }

    // =========================================================================
    // 播放器：进度拖动 / 倍速 / 暂停 / 快进快退
    // =========================================================================
    private fun setupPlayer() {
        sbSpeed.max = SPEED_STEPS - 1
        val idx = speedToIndex(prefs.getFloat("play_speed", 1.0f))
        sbSpeed.progress = idx
        tvSpeed.text = fmtSpeed(indexToSpeed(idx))

        sbSpeed.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(seekBar: SeekBar?, progress: Int, fromUser: Boolean) {
                tvSpeed.text = fmtSpeed(indexToSpeed(progress))
                if (fromUser) applySpeed(indexToSpeed(progress))
            }

            override fun onStartTrackingTouch(seekBar: SeekBar?) {}

            override fun onStopTrackingTouch(seekBar: SeekBar?) {
                val s = indexToSpeed(sbSpeed.progress)
                prefs.edit().putFloat("play_speed", s).apply()
                applySpeed(s)
            }
        })

        sbPos.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(seekBar: SeekBar?, progress: Int, fromUser: Boolean) {
                if (fromUser) tvTime.text = timePair(progress.toLong(), durationMs())
            }

            override fun onStartTrackingTouch(seekBar: SeekBar?) {
                userSeeking = true
            }

            override fun onStopTrackingTouch(seekBar: SeekBar?) {
                userSeeking = false
                val p = player ?: return
                try {
                    p.seekTo(sbPos.progress)
                } catch (_: Exception) {
                    // 播放器已被释放，忽略
                }
                tvTime.text = timePair(sbPos.progress.toLong(), durationMs())
            }
        })
    }

    private fun indexToSpeed(index: Int): Float =
        SPEED_MIN + SPEED_STEP * index.coerceIn(0, SPEED_STEPS - 1)

    private fun speedToIndex(speed: Float): Int =
        Math.round((speed - SPEED_MIN) / SPEED_STEP).coerceIn(0, SPEED_STEPS - 1)

    private fun currentSpeed(): Float = indexToSpeed(sbSpeed.progress)

    private fun fmtSpeed(s: Float): String = String.format(Locale.US, "%.1fx", s)

    /**
     * 应用倍速。pitch 固定 1.0 保持人声不变调。
     * 注意：部分机型在「暂停状态」下调用 setPlaybackParams 会自己开始播放，
     * 所以要记下原状态，设完再按回去。
     */
    private fun applySpeed(speed: Float) {
        val p = player ?: return
        try {
            val wasPaused = !p.isPlaying
            p.playbackParams = PlaybackParams().setSpeed(speed).setPitch(1.0f)
            if (wasPaused) p.pause()
        } catch (_: Exception) {
            // 极少数机型不支持变速：忽略，按原速播放不受影响
        }
    }

    private val ticker = object : Runnable {
        override fun run() {
            if (!isPlaying()) return
            syncSeekMax()
            if (!userSeeking) {
                val pos = currentPosition()
                sbPos.progress = pos
                tvTime.text = timePair(pos.toLong(), durationMs())
            }
            ui.postDelayed(this, TICK_MS)
        }
    }

    private fun startTicker() {
        ui.removeCallbacks(ticker)
        ui.post(ticker)
    }

    private fun stopTicker() = ui.removeCallbacks(ticker)

    private fun isPlaying(): Boolean = try {
        player?.isPlaying == true
    } catch (_: Exception) {
        false
    }

    private fun currentPosition(): Int = try {
        player?.currentPosition ?: 0
    } catch (_: Exception) {
        0
    }

    private fun durationMs(): Long {
        val d = try {
            player?.duration ?: 0
        } catch (_: Exception) {
            0
        }
        return if (d > 0) d.toLong() else 0L
    }

    /** 让进度条的量程跟上真实时长（时长未知时保持原样） */
    private fun syncSeekMax() {
        val d = durationMs()
        if (d > 0 && sbPos.max != d.toInt()) sbPos.max = d.toInt()
    }

    private fun timePair(posMs: Long, durMs: Long): String {
        val hi = if (durMs > 0) durMs else posMs.coerceAtLeast(0L)
        return fmtTime(posMs.coerceIn(0L, hi)) + " / " + fmtTime(durMs)
    }

    private fun fmtTime(ms: Long): String {
        val total = (ms / 1000).coerceAtLeast(0L)
        return String.format(Locale.US, "%02d:%02d", total / 60, total % 60)
    }

    /** 只读文件时长，不启动播放（失败返回 0） */
    private fun probeDurationMs(path: String): Int = try {
        val mp = MediaPlayer()
        mp.setDataSource(path)
        mp.prepare()
        val d = mp.duration
        mp.release()
        if (d > 0) d else 0
    } catch (_: Exception) {
        0
    }

    private fun wireButtons() {
        findViewById<Button>(R.id.btnPick).setOnClickListener { pickImages() }
        findViewById<Button>(R.id.btnSaveKey).setOnClickListener {
            val k = etKey.text.toString().trim()
            if (k.length < 20) {
                tvKeyMsg.text = "Key 太短，请确认完整复制（智谱 Key 约 40~50 位）"
                tvKeyMsg.setTextColor(getColor(R.color.err))
            } else {
                prefs.edit().putString("api_key", k).apply()
                tvKeyMsg.text = "已保存到本机，无需重复填写"
                tvKeyMsg.setTextColor(getColor(R.color.ok))
            }
        }
        btnGen.setOnClickListener { doGenerate() }
        btnResynth.setOnClickListener { doResynth() }
        btnPlay.setOnClickListener { togglePlayPause() }
        btnShare.setOnClickListener { shareAudio() }

        findViewById<Button>(R.id.btnBack5).setOnClickListener { nudge(-JUMP_MS) }
        findViewById<Button>(R.id.btnFwd5).setOnClickListener { nudge(JUMP_MS) }
        findViewById<Button>(R.id.btnExternal).setOnClickListener { openInSystemPlayer() }
    }

    // =========================================================================
    // 音色表（由 Python 侧读取内置 voices.json 返回）
    // =========================================================================
    private fun loadVoicesFromPython() {
        status("正在加载音色表…", false)
        Thread {
            try {
                loadBuiltinKey()
                val root = JSONObject(PyBridge.voicesJson())
                val arr = root.getJSONArray("languages")
                val list = ArrayList<Lang>()
                for (i in 0 until arr.length()) {
                    val o = arr.getJSONObject(i)
                    val va = o.getJSONArray("voices")
                    val vs = ArrayList<Voice>()
                    for (j in 0 until va.length()) {
                        val v = va.getJSONObject(j)
                        vs.add(
                            Voice(
                                v.getString("id"),
                                v.optString("nick", v.getString("id")),
                                v.optString("gender", "")
                            )
                        )
                    }
                    if (vs.isEmpty()) continue
                    list.add(
                        Lang(
                            o.getString("code"),
                            o.getString("label"),
                            o.optString("prompt_name", o.getString("label")),
                            vs
                        )
                    )
                }
                runOnUiThread { applyLanguages(list) }
            } catch (e: Exception) {
                runOnUiThread { status("音色表加载失败：" + e.message, true) }
            }
        }.start()
    }

    private fun applyLanguages(list: List<Lang>) {
        langs = list
        if (list.isEmpty()) {
            status("音色表为空", true)
            return
        }
        spLang.adapter = spinnerAdapter(list.map { it.label })
        spLang.onItemSelectedListener = object : SimpleItemSelectedListener() {
            override fun onSelected(position: Int) {
                rebuildVoiceSpinner()
            }
        }

        val saved = prefs.getString("lang_code", "zh-CN")
        val idx = list.indexOfFirst { it.code == saved }.let { if (it >= 0) it else 0 }
        spLang.setSelection(idx)
        rebuildVoiceSpinner()

        val key = prefs.getString("api_key", "") ?: ""
        status(
            if (key.length >= 20) "环境就绪：点①选图片，点③开始生成"
            else "环境就绪：请先填写智谱 API Key",
            false
        )
    }

    private fun rebuildVoiceSpinner() {
        val lang = currentLang() ?: return
        prefs.edit().putString("lang_code", lang.code).apply()
        val labels = lang.voices.map { "${it.nick} · ${it.gender}" }
        spVoice.adapter = spinnerAdapter(labels)

        val savedVoice = prefs.getString("voice_id", "")
        val vi = lang.voices.indexOfFirst { it.id == savedVoice }
        if (vi >= 0) spVoice.setSelection(vi)
        spVoice.onItemSelectedListener = object : SimpleItemSelectedListener() {
            override fun onSelected(position: Int) {
                lang.voices.getOrNull(position)?.let {
                    prefs.edit().putString("voice_id", it.id).apply()
                }
            }
        }
    }

    private fun currentLang(): Lang? = langs.getOrNull(spLang.selectedItemPosition)

    private fun currentVoice(): Voice? {
        val lang = currentLang() ?: return null
        return lang.voices.getOrNull(spVoice.selectedItemPosition)
    }

    private fun currentRate(): Int = sbRate.progress - 30

    // =========================================================================
    // 选图
    // =========================================================================
    private fun pickImages() {
        val i = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            type = "image/*"
            putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or
                    Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION)
        }
        startActivityForResult(Intent.createChooser(i, "选择图片（最多 $MAX_IMAGES 张）"), REQ_PICK)
    }

    @Deprecated("沿用系统原生选图，避免引入 AndroidX Activity 依赖")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != REQ_PICK || resultCode != RESULT_OK || data == null) return

        pickedUris.clear()
        val clip = data.clipData
        if (clip != null) {
            // ClipData 没有 count 属性，正确的是 itemCount（即 getItemCount()）
            for (i in 0 until minOf(clip.itemCount, MAX_IMAGES)) {
                pickedUris.add(clip.getItemAt(i).uri)
            }
        } else {
            data.data?.let { pickedUris.add(it) }
        }
        for (u in pickedUris) {
            try {
                contentResolver.takePersistableUriPermission(
                    u, Intent.FLAG_GRANT_READ_URI_PERMISSION
                )
            } catch (_: Exception) {
                // 部分来源不支持持久授权，忽略
            }
        }
        tvPick.text = "已选择 ${pickedUris.size} 张"
        tvPick.setTextColor(getColor(R.color.ok))
    }

    // =========================================================================
    // 生成 / 重新合成
    // =========================================================================
    private fun doGenerate() {
        val key = etKey.text.toString().trim()
        if (key.length < 20) {
            status("请先填写智谱 API Key 并点“保存”", true)
            return
        }
        if (pickedUris.isEmpty()) {
            status("请先点“① 选择图片”", true)
            return
        }
        val lang = currentLang() ?: return
        val voice = currentVoice() ?: return
        val mode = MODE_CODES[spMode.selectedItemPosition]
        val detail = DETAIL_CODES[spDetail.selectedItemPosition]
        val rate = currentRate()
        prefs.edit().putString("api_key", key).apply()

        setBusy(true, "正在识别图片并合成语音…（约 5~60 秒，请勿关闭）")
        Thread {
            try {
                val inDir = File(filesDir, "in").apply { mkdirs() }
                val outDir = File(filesDir, "out").apply { mkdirs() }
                val paths = ArrayList<String>()
                pickedUris.forEachIndexed { idx, uri ->
                    ImageUtil.uriToJpeg(this, uri, inDir, idx)?.let { paths.add(it) }
                }
                if (paths.isEmpty()) throw RuntimeException("图片读取失败，请重新选择图片")

                val r = PyBridge.generate(
                    paths, lang.code, voice.id, rate, mode, detail, key, outDir.absolutePath
                )
                runOnUiThread { handleResult(r, "生成完成") }
            } catch (e: Exception) {
                runOnUiThread {
                    setBusy(false, "")
                    status("出错：" + friendly(e), true)
                }
            }
        }.start()
    }

    private fun doResynth() {
        val text = etText.text.toString().trim()
        if (text.isEmpty()) {
            status("文字稿为空，无法合成", true)
            return
        }
        val voice = currentVoice() ?: return
        val rate = currentRate()
        setBusy(true, "正在合成语音…（约 3~20 秒）")
        Thread {
            try {
                val outDir = File(filesDir, "out").apply { mkdirs() }
                val r = PyBridge.resynth(text, voice.id, rate, outDir.absolutePath)
                runOnUiThread { handleResult(r, "重新合成完成") }
            } catch (e: Exception) {
                runOnUiThread {
                    setBusy(false, "")
                    status("出错：" + friendly(e), true)
                }
            }
        }.start()
    }

    private fun handleResult(r: JSONObject, okTitle: String) {
        setBusy(false, "")
        if (!r.optBoolean("ok", false)) {
            status(r.optString("error", "未知错误"), true)
            return
        }
        val text = r.optString("text", "")
        if (text.isNotEmpty()) etText.setText(text)

        // 出了新音频：先停掉旧的，避免两个声音叠在一起
        releasePlayer()
        lastMp3 = r.optString("mp3", "").ifEmpty { null }
        lastMp3?.let { prefs.edit().putString("last_mp3", it).apply() }
        lastMp3?.let { showPlayer(it) }

        val note = r.optString("note", "")
        status(
            if (note.isEmpty()) "$okTitle，点“▶ 播放”试听" else "$okTitle（$note）",
            false
        )
        tvResult.text = buildString {
            append("音频：").append(File(lastMp3 ?: "").name).append('\n')
            r.optString("srt", "").takeIf { it.isNotEmpty() }?.let {
                append("字幕：").append(File(it).name).append('\n')
            }
            append("文件目录：").append(filesDir.absolutePath).append("/out")
        }
    }

    /** 亮出播放器面板，并把进度条量程与时长对齐 */
    private fun showPlayer(path: String) {
        playerBox.visibility = View.VISIBLE
        btnPlay.text = getString(R.string.play)
        tvTime.text = timePair(0, 0)
        sbPos.progress = 0
        sbPos.max = 100
        val d = probeDurationMs(path)
        if (d > 0) {
            sbPos.max = d
            tvTime.text = timePair(0, d.toLong())
        }
    }

    /** 上次生成过的音频，重开 App 后仍可继续播放 */
    private fun restoreLastAudio() {
        val p = prefs.getString("last_mp3", "") ?: ""
        if (p.isEmpty() || !File(p).exists()) return
        lastMp3 = p
        showPlayer(p)
    }

    // =========================================================================
    // 播放 / 分享
    // =========================================================================
    /** 创建并 prepare 播放器（不自动播放）。已有实例则直接复用。 */
    private fun ensurePlayer(): MediaPlayer? {
        player?.let { return it }
        val path = lastMp3 ?: return null
        return try {
            val mp = MediaPlayer()
            mp.setDataSource(path)
            mp.prepare()
            mp.setOnCompletionListener { onPlayCompleted() }
            player = mp
            syncSeekMax()
            mp
        } catch (e: Exception) {
            status("播放失败：" + friendly(e), true)
            releasePlayer()
            null
        }
    }

    private fun togglePlayPause() {
        if (lastMp3.isNullOrEmpty()) {
            status("还没有可播放的音频", true)
            return
        }
        val p = ensurePlayer() ?: return

        if (isPlaying()) {
            try {
                p.pause()
            } catch (_: Exception) {
            }
            stopTicker()
            btnPlay.text = getString(R.string.play)
            val pos = currentPosition()
            sbPos.progress = pos
            tvTime.text = timePair(pos.toLong(), durationMs())
            return
        }

        // 播完后再点“播放”：从头开始
        val dur = durationMs()
        val pos = currentPosition()
        if (dur > 0 && pos >= dur - 300) {
            try {
                p.seekTo(0)
            } catch (_: Exception) {
            }
        }
        try {
            p.start()
        } catch (e: Exception) {
            status("播放失败：" + friendly(e), true)
            releasePlayer()
            return
        }
        applySpeed(currentSpeed())
        btnPlay.text = getString(R.string.pause)
        startTicker()
    }

    private fun onPlayCompleted() {
        stopTicker()
        btnPlay.text = getString(R.string.play)
        sbPos.progress = 0
        tvTime.text = timePair(0, durationMs())
    }

    /** 快进/快退：deltaMs 为正表示前进 */
    private fun nudge(deltaMs: Int) {
        if (lastMp3.isNullOrEmpty()) {
            status("还没有可播放的音频", true)
            return
        }
        val p = ensurePlayer() ?: return
        val dur = durationMs()
        var target = currentPosition() + deltaMs
        if (target < 0) target = 0
        if (dur > 0 && target > dur) target = dur.toInt()
        try {
            p.seekTo(target)
        } catch (_: Exception) {
            return
        }
        sbPos.progress = target
        tvTime.text = timePair(target.toLong(), dur)
    }

    /** 交给手机自带的默认播放器打开（可后台播放、能进音乐 App 的列表） */
    private fun openInSystemPlayer() {
        val path = lastMp3
        if (path.isNullOrEmpty() || !File(path).exists()) {
            status("还没有可播放的音频", true)
            return
        }
        if (isPlaying()) {
            try {
                player?.pause()
            } catch (_: Exception) {
            }
            stopTicker()
            btnPlay.text = getString(R.string.play)
        }
        try {
            val uri = FileProvider.getUriForFile(this, "$packageName.fileprovider", File(path))
            val i = Intent(Intent.ACTION_VIEW).apply {
                setDataAndType(uri, "audio/mpeg")
                addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            }
            startActivity(Intent.createChooser(i, "用系统播放器打开"))
        } catch (e: Exception) {
            status("没有找到可用的播放器：" + friendly(e), true)
        }
    }

    private fun releasePlayer() {
        stopTicker()
        try {
            player?.stop()
        } catch (_: Exception) {
        }
        try {
            player?.release()
        } catch (_: Exception) {
        }
        player = null
        btnPlay.text = getString(R.string.play)
    }

    private fun shareAudio() {
        val path = lastMp3
        if (path.isNullOrEmpty() || !File(path).exists()) {
            status("还没有可分享的音频", true)
            return
        }
        try {
            val uri = FileProvider.getUriForFile(
                this, "$packageName.fileprovider", File(path)
            )
            val i = Intent(Intent.ACTION_SEND).apply {
                type = "audio/mpeg"
                putExtra(Intent.EXTRA_STREAM, uri)
                addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            }
            startActivity(Intent.createChooser(i, "分享音频"))
        } catch (e: Exception) {
            status("分享失败：" + friendly(e), true)
        }
    }

    // =========================================================================
    // 小工具
    // =========================================================================
    private fun setBusy(busy: Boolean, msg: String) {
        btnGen.isEnabled = !busy
        btnResynth.isEnabled = !busy
        findViewById<Button>(R.id.btnPick).isEnabled = !busy
        if (busy) status(msg, false)
    }

    private fun status(msg: String, isError: Boolean) {
        tvStatus.text = msg
        tvStatus.setTextColor(getColor(if (isError) R.color.err else R.color.brand_dark))
        if (isError) Toast.makeText(this, msg, Toast.LENGTH_LONG).show()
    }

    /** 把 Python 抛过来的长异常压缩成一行可读提示 */
    private fun friendly(e: Throwable): String {
        val m = e.message ?: e.toString()
        val one = m.lineSequence().map { it.trim() }.filter { it.isNotEmpty() }
            .lastOrNull() ?: m
        return one.take(300)
    }

    private fun restoreKey() {
        val k = prefs.getString("api_key", "") ?: ""
        if (k.isNotEmpty()) {
            etKey.setText(k)
            tvKeyMsg.text = "已读取本机保存的 Key"
            tvKeyMsg.setTextColor(getColor(R.color.muted))
        }
    }

    /**
     * 本机没存过 Key 时，读取 App 内置的 Key 自动填入。
     * 内置 Key 由 CI 从仓库 Secret 注入，用不着用户手输；没配就静默跳过。
     * 必须在后台线程调用（会触发 Python 初始化）。
     */
    private fun loadBuiltinKey() {
        if (etKey.text.toString().trim().length >= 20) return
        try {
            val o = PyBridge.defaultKey()
            val k = o.optString("key", "")
            if (!o.optBoolean("ok", false) || k.length < 20) return
            prefs.edit().putString("api_key", k).apply()
            runOnUiThread {
                etKey.setText(k)
                tvKeyMsg.text = "已内置 Key（" + o.optString("masked", "") +
                        "），可直接使用；也可粘贴你自己的 Key 覆盖"
                tvKeyMsg.setTextColor(getColor(R.color.ok))
            }
        } catch (_: Exception) {
            // 没有内置 Key 或 Python 尚未就绪：保持手动输入
        }
    }

    /** Spinner 选中回调的最小实现（避免额外抽象类） */
    private abstract class SimpleItemSelectedListener :
        android.widget.AdapterView.OnItemSelectedListener {
        abstract fun onSelected(position: Int)

        override fun onItemSelected(
            parent: android.widget.AdapterView<*>?, view: View?, position: Int, id: Long
        ) = onSelected(position)

        override fun onNothingSelected(parent: android.widget.AdapterView<*>?) {}
    }
}
