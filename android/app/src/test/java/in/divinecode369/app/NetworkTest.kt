package `in`.divinecode369.app

import `in`.divinecode369.app.core.SessionInterceptor
import `in`.divinecode369.app.core.secureHttpClient
import okhttp3.*
import okio.Buffer
import org.junit.Assert.*
import org.junit.Test
import java.util.concurrent.TimeUnit

/** An in-process terminal interceptor captures requests without using live services. */
class NetworkTest {
    private var captured:Request?=null
    private fun client()=OkHttpClient.Builder().addInterceptor(SessionInterceptor({"synthetic-device-credential"},"https://divinecode369.in/"))
        .addInterceptor { chain->captured=chain.request();Response.Builder().request(chain.request()).protocol(Protocol.HTTP_1_1).code(200).message("Fixture").body(ResponseBody.create(null,"{}" )).build() }.build()
    private fun execute(path:String)=client().newCall(Request.Builder().url("https://divinecode369.in$path").header("Authorization","injected").header("Cookie","injected").build()).execute().close()
    @Test fun publicAndProviderRoutesNeverReceiveDeviceSecrets() {
        for(path in listOf("/api/v1/mobile/ipos","/api/v1/mobile/overview","/auth/mobile/refresh","/api/connections/kite/disconnect")) {
            execute(path);assertNull(captured!!.header("Authorization"));assertNull(captured!!.header("Cookie"))
        }
    }
    @Test fun onlyScopedPersonalRoutesReceiveAccessCredential() {
        for(path in listOf("/api/v1/mobile/watchlist","/api/v1/mobile/alerts/inbox","/api/v1/mobile/preferences","/api/v1/mobile/history/NSE:FIXTURE","/auth/mobile/logout")) {
            execute(path);assertEquals("Bearer synthetic-device-credential",captured!!.header("Authorization"))
        }
    }
    @Test fun otherHostsAndCleartextFailBeforeSending() {
        for(url in listOf("http://divinecode369.in/api/v1/mobile/watchlist","https://evil.example/api/v1/mobile/watchlist","https://divinecode369.in:444/api/v1/mobile/watchlist")) {
            assertThrows(IllegalStateException::class.java) { client().newCall(Request.Builder().url(url).build()).execute() }
        }
        assertNull(captured)
    }
    @Test fun redirectsAreDisabledInProductionConfiguration() {
        val configured=secureHttpClient(SessionInterceptor({null},"https://divinecode369.in/"))
        assertFalse(configured.followRedirects);assertFalse(configured.followSslRedirects);assertFalse(configured.retryOnConnectionFailure)
    }
}
