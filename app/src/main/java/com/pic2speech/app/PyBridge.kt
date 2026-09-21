package com.pic2speech.app

import com.chaquo.python.PyObject
import com.chaquo.python.Python
import org.json.JSONObject

/**
 * Kotlin <-> Python 桥接层
 *
 * 设计原则：**所有跨语言参数都是字符串 / 整数**，Python 侧统一返回 JSON 字符串。
 * 这样完全避开了二进制数组跨 JNI 传递的兼容问题，出错也只会是普通的字符串消息。
 *
 * 注意：所有方法都是阻塞的，必须在后台线程调用。
 */
object PyBridge {

    @Volatile
    private var module: PyObject? = null

    private fun api(): PyObject {
        var m = module
        if (m == null) {
            m = Python.getInstance().getModule("pic2speech.api")
            module = m
        }
        return m
    }

    /** 读取内置的多语言音色表（JSON 字符串） */
    fun voicesJson(): String = api().callAttr("voices_json").toString()

    /**
     * 读取 App 内置的默认 API Key（构建时由仓库 Secret 注入）。
     * @return {"ok":true,"key":"...","masked":"40edcc***ie1Gq","builtin":true}
     */
    fun defaultKey(): JSONObject = JSONObject(api().callAttr("default_key").toString())

    /**
     * 完整流程：图片理解 + 语音合成
     * @return {"ok":true,"text":...,"mp3":...,"srt":...,"note":...}
     *         或 {"ok":false,"error":"..."}
     */
    fun generate(
        imagePaths: List<String>,
        langCode: String,
        voiceId: String,
        rate: Int,
        mode: String,
        detail: String,
        apiKey: String,
        outDir: String
    ): JSONObject {
        val res = api().callAttr(
            "generate",
            imagePaths.toTypedArray(),
            langCode,
            voiceId,
            rate,
            mode,
            detail,
            apiKey,
            outDir
        )
        return JSONObject(res.toString())
    }

    /** 用界面上编辑后的文字重新合成（不重新识别图片） */
    fun resynth(text: String, voiceId: String, rate: Int, outDir: String): JSONObject {
        val res = api().callAttr("resynth", text, voiceId, rate, outDir)
        return JSONObject(res.toString())
    }
}
