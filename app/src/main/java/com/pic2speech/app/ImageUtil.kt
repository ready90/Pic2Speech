package com.pic2speech.app

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import java.io.File

/**
 * 图片压缩：图片 Uri -> 最长边 1568 的 JPEG 文件
 *
 * 压缩放在 Kotlin 侧做，是为了让 Python 侧彻底不需要 Pillow
 * （Pillow 是 C 扩展，能装但没必要，少一个原生依赖少一份风险）。
 */
object ImageUtil {

    private const val MAX_SIDE = 1568
    private const val QUALITY = 88

    /** 返回压缩后的 JPEG 绝对路径；失败返回 null */
    fun uriToJpeg(ctx: Context, uri: Uri, outDir: File, index: Int): String? {
        return try {
            val src = ctx.contentResolver.openInputStream(uri)?.use {
                BitmapFactory.decodeStream(it)
            } ?: return null

            val scale = minOf(1f, MAX_SIDE.toFloat() / maxOf(src.width, src.height))
            val dst = if (scale < 1f) {
                Bitmap.createScaledBitmap(
                    src,
                    (src.width * scale).toInt().coerceAtLeast(1),
                    (src.height * scale).toInt().coerceAtLeast(1),
                    true
                )
            } else {
                src
            }

            outDir.mkdirs()
            val f = File(outDir, "in_$index.jpg")
            f.outputStream().use { os ->
                dst.compress(Bitmap.CompressFormat.JPEG, QUALITY, os)
            }
            if (dst !== src) dst.recycle()
            src.recycle()
            f.absolutePath
        } catch (e: Exception) {
            null
        }
    }
}
