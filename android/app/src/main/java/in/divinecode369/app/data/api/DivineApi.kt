package `in`.divinecode369.app.data.api

import kotlinx.serialization.json.JsonObject
import retrofit2.http.*

interface DivineApi {
    @GET("api/v1/mobile/overview") suspend fun overview(): Overview
    @GET("api/v1/mobile/scanner") suspend fun scanner(@Query("match") match: String = "universe", @Query("page_size") size: Int = 100, @Query("page") page: Int = 1): StockPage
    @GET("api/v1/mobile/sectors") suspend fun sectors(): SectorPage
    @GET("api/v1/mobile/sectors/{id}") suspend fun sector(@Path("id") id: String): Sector
    @GET("api/v1/mobile/stocks/{symbol}") suspend fun stock(@Path("symbol") symbol: String): Stock
    @GET("api/v1/mobile/ipos") suspend fun ipos(@Query("phase") phase: String, @Query("board") board: String, @Query("search") search: String, @Query("page") page: Int, @Query("page_size") size: Int = 20, @Query("sort") sort: String = "schedule"): IPOPage
    @GET("api/v1/mobile/ipos/{slug}") suspend fun ipo(@Path("slug") slug: String): IPODetail
    @GET("api/v1/mobile/ipos/{slug}/{kind}") suspend fun resource(@Path("slug") slug: String, @Path("kind") kind: String): Resource
    @GET("api/v1/mobile/watchlist") suspend fun watchlist(): Watchlist
    @PUT("api/v1/mobile/watchlist") suspend fun save(@Body item: SavedItem): Watchlist
    @GET("api/v1/mobile/alerts") suspend fun alerts(): AlertRules
    @PUT("api/v1/mobile/alerts") suspend fun saveAlert(@Body rule: AlertRule): AlertRules
    @DELETE("api/v1/mobile/alerts/{id}") suspend fun deleteAlert(@Path("id") id: String): AlertRules
    @GET("api/v1/mobile/alerts/inbox") suspend fun inbox(): AlertInbox
    @GET("api/v1/mobile/preferences") suspend fun preferences(): Preferences
    @PUT("api/v1/mobile/preferences") suspend fun preferences(@Body value: Preferences): Preferences
    @GET("api/v1/mobile/history/{symbol}") suspend fun history(@Path("symbol") symbol: String): History
    @GET("api/v1/mobile/predictions") suspend fun predictions(): JsonObject
    @GET("api/v1/mobile/intelligence") suspend fun intelligence(@Query("context_symbols") symbols:String):JsonObject
    @POST("auth/mobile/start") suspend fun start(@Body body: DeviceStart): DeviceStarted
    @POST("auth/mobile/token") suspend fun token(@Body body: DeviceGrant): MobileTokens
    @POST("auth/mobile/refresh") suspend fun refresh(@Body body: RefreshGrant): MobileTokens
    @POST("auth/mobile/logout") suspend fun logout(): JsonObject
}
