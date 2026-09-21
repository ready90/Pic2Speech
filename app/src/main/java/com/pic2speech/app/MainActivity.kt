package com.pic2speech.app

import android.app.Activity
import android.content.Intent
import android.media.MediaPlayer
import android.net.Uri
import android.os.Bundle
import android.view.View
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.EditText
import android.widget.SeekBar
import android.widget.Spinner
import android.widget.TextView
import android.widget.Toast
import androidx.core.content.FileProvider
import org.json.JSONObject
import java.io.File

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

    // ---------- 状态 ----------
    private val pickedUris = mutableListOf<Uri>()
    private var langs: List<Lang> = emptyList()
    private var lastMp3: String? = null
    private var player: MediaPlayer? = null

    private val prefs by lazy { getSharedPreferences("pic2speech", MODE_PRIVATE) }

    companion object {
        private const val REQ_PICK = 1001
        private const val MAX_IMAGES = 8
        private val MODE_LABELS = listOf("看图解说", "朗读图中文字", "翻译朗读")
        private val MODE_CODES = listOf("talk", "read", "trans")
        private val DETAIL_LABELS = listOf("简洁", "标准", "详细")
        private val DETAIL_CODES = listOf("short", "standard", "long")
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
        wireButtons()
        restoreKey()
        loadVoicesFromPython()
    }

    override fun onDestroy() {
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
        btnPlay.setOnClickListener { togglePlay() }
        btnShare.setOnClickListener { shareAudio() }
    }

    // =========================================================================
    // 音色表（由 Python 侧读取内置 voices.json 返回）
    // =========================================================================
    private fun loadVoicesFromPython() {
        status("正在加载音色表…", false)
        Thread {
            try {
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
        lastMp3 = r.optString("mp3", "").ifEmpty { null }
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

    // =========================================================================
    // 播放 / 分享
    // =========================================================================
    private fun togglePlay() {
        val path = lastMp3
        if (path.isNullOrEmpty()) {
            status("还没有可播放的音频", true)
            return
        }
        if (player?.isPlaying == true) {
            releasePlayer()
            btnPlay.text = getString(R.string.play)
            return
        }
        try {
            releasePlayer()
            player = MediaPlayer().apply {
                setDataSource(path)
                prepare()
                setOnCompletionListener {
                    btnPlay.text = getString(R.string.play)
                }
                start()
            }
            btnPlay.text = getString(R.string.stop)
        } catch (e: Exception) {
            status("播放失败：" + friendly(e), true)
        }
    }

    private fun releasePlayer() {
        try {
            player?.stop()
        } catch (_: Exception) {
        }
        try {
            player?.release()
        } catch (_: Exception) {
        }
        player = null
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
