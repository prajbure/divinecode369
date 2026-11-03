package `in`.divinecode369.app.core

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import dagger.hilt.android.qualifiers.ApplicationContext
import `in`.divinecode369.app.data.api.MobileTokens
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import java.security.KeyStore
import java.security.MessageDigest
import java.security.SecureRandom
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import javax.inject.Inject
import javax.inject.Singleton

/** The provider keys and backend admin token never enter this process. */
@Singleton
class SessionStore @Inject constructor(@ApplicationContext context: Context) {
    private val prefs = context.getSharedPreferences("encrypted_session", Context.MODE_PRIVATE)
    private val json = Json { ignoreUnknownKeys = true }
    private val alias = "divine_device_session_v1"
    private val _signedIn = MutableStateFlow(false)
    val signedIn = _signedIn.asStateFlow()
    @Volatile private var tokens: MobileTokens? = null
    @Volatile var expiresAt: Long = 0; private set

    init {
        try {
            val encrypted = prefs.getString("ciphertext", null)
            val iv = prefs.getString("iv", null)
            if (encrypted != null && iv != null) {
                val cipher = Cipher.getInstance("AES/GCM/NoPadding")
                cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, Base64.decode(iv, Base64.NO_WRAP)))
                tokens = json.decodeFromString<MobileTokens>(cipher.doFinal(Base64.decode(encrypted, Base64.NO_WRAP)).toString(Charsets.UTF_8))
                expiresAt = prefs.getLong("expires_at", 0)
                _signedIn.value = true
            }
        } catch (_: Exception) { clear() }
    }
    private fun key(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey(alias, null) as? SecretKey)?.let { return it }
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").apply {
            init(KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).setRandomizedEncryptionRequired(true).build())
        }.generateKey()
    }
    fun access(): String? = tokens?.access_token
    fun refresh(): String? = tokens?.refresh_token
    @Synchronized fun save(value: MobileTokens) {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding"); cipher.init(Cipher.ENCRYPT_MODE, key())
        val encrypted = cipher.doFinal(json.encodeToString(value).toByteArray())
        val expiry = System.currentTimeMillis() + value.expires_in * 1000L
        check(prefs.edit().putString("ciphertext", Base64.encodeToString(encrypted, Base64.NO_WRAP)).putString("iv", Base64.encodeToString(cipher.iv, Base64.NO_WRAP)).putLong("expires_at", expiry).commit())
        tokens = value; expiresAt = expiry; _signedIn.value = true
    }
    @Synchronized fun clear() {
        tokens = null; expiresAt = 0; _signedIn.value = false
        val removed=prefs.edit().clear().commit()
        val destroyed=runCatching { KeyStore.getInstance("AndroidKeyStore").apply{load(null)}.deleteEntry(alias) }.isSuccess
        check(removed||destroyed) { "Device session cleanup failed. Revoke this device from owner Settings." }
    }
}

object DeviceProof {
    fun verifier(): String = encode(ByteArray(48).also { SecureRandom().nextBytes(it) })
    fun challenge(verifier: String): String = encode(MessageDigest.getInstance("SHA-256").digest(verifier.toByteArray(Charsets.US_ASCII)))
    private fun encode(bytes: ByteArray) = java.util.Base64.getUrlEncoder().withoutPadding().encodeToString(bytes)
}
