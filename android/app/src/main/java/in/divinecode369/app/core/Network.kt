package `in`.divinecode369.app.core

import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import `in`.divinecode369.app.BuildConfig
import `in`.divinecode369.app.data.api.DivineApi
import `in`.divinecode369.app.data.api.RefreshGrant
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.serialization.json.Json
import okhttp3.Interceptor
import okhttp3.OkHttpClient
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.MediaType.Companion.toMediaType
import retrofit2.Retrofit
import retrofit2.HttpException
import retrofit2.converter.kotlinx.serialization.asConverterFactory
import java.util.concurrent.TimeUnit
import javax.inject.Inject
import javax.inject.Singleton

class SessionInterceptor(private val access: () -> String?, private val canonical: String) : Interceptor {
    override fun intercept(chain: Interceptor.Chain): okhttp3.Response {
        val request = chain.request(); val base = canonical.toHttpUrl()
        check(request.url.scheme == "https" && request.url.host == base.host && request.url.port == base.port) { "Untrusted API destination" }
        val path = request.url.encodedPath
        val personal = path.startsWith("/api/v1/mobile/") && (path.substringAfter("/api/v1/mobile/").substringBefore('/') in setOf("watchlist","alerts","preferences","history","predictions"))
        val builder = request.newBuilder().removeHeader("Authorization").removeHeader("Cookie")
        val research=path=="/api/v1/mobile/intelligence"&&!request.url.queryParameter("context_symbols").isNullOrBlank()
        if (personal || research || path == "/auth/mobile/logout") access()?.let { builder.header("Authorization", "Bearer $it") }
        return chain.proceed(builder.header("Accept", "application/json").build())
    }
}

@Module @InstallIn(SingletonComponent::class)
object NetworkModule {
    @Provides @Singleton fun json() = Json { ignoreUnknownKeys = true; explicitNulls = false; isLenient = false }
    @Provides @Singleton fun http(sessions: SessionStore): OkHttpClient = secureHttpClient(SessionInterceptor(sessions::access, BuildConfig.API_BASE_URL))
    @Provides @Singleton fun api(client: OkHttpClient, json: Json): DivineApi = Retrofit.Builder().baseUrl(BuildConfig.API_BASE_URL)
        .client(client).addConverterFactory(json.asConverterFactory("application/json".toMediaType())).build().create(DivineApi::class.java)
}

fun secureHttpClient(interceptor:Interceptor):OkHttpClient = OkHttpClient.Builder().addInterceptor(interceptor)
    .followRedirects(false).followSslRedirects(false).retryOnConnectionFailure(false)
    .connectTimeout(15,TimeUnit.SECONDS).readTimeout(25,TimeUnit.SECONDS).callTimeout(35,TimeUnit.SECONDS).build()

@Singleton class AuthenticatedCall @Inject constructor(private val api: DivineApi, private val sessions: SessionStore) {
    private val lock = Mutex()
    private suspend fun renew(expected: String?) = lock.withLock {
        if (sessions.access() != expected) return@withLock
        val refresh = sessions.refresh() ?: error("Sign in to sync your account.")
        try { sessions.save(api.refresh(RefreshGrant(refresh))) }
        catch (e: HttpException) { if (e.code() in listOf(400,401,403)) sessions.clear(); throw e }
    }
    suspend fun <T> run(action: suspend () -> T): T {
        if (sessions.access() == null) error("Sign in to sync your account.")
        if (System.currentTimeMillis() >= sessions.expiresAt - 30_000) renew(sessions.access())
        val access = sessions.access()
        return try { action() } catch (e: HttpException) { if(e.code()!=401) throw e; renew(access); action() }
    }
}

fun readableError(error: Throwable): String = when(error) {
    is HttpException -> when(error.code()) { 401 -> "Session expired. Sign in again.";403 -> "This action is not authorized.";429 -> "Request limit reached. Try again shortly.";in 500..599 -> "Backend unavailable. Try again.";else -> "Request could not be completed (${error.code()})." }
    is java.io.IOException -> "Offline. Reconnect to refresh data."
    else -> "Could not complete this action. Try again."
}
