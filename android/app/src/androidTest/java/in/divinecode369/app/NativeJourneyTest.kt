package `in`.divinecode369.app

import android.content.Context
import android.content.ContextWrapper
import androidx.activity.ComponentActivity
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.lifecycle.*
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import `in`.divinecode369.app.core.*
import `in`.divinecode369.app.data.*
import `in`.divinecode369.app.data.api.*
import `in`.divinecode369.app.ui.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.serialization.json.*
import org.junit.*
import org.junit.runner.RunWith
import java.io.IOException
import java.lang.reflect.Proxy

/** Dedicated emulator only. All network responses are synthetic in-process values. */
@RunWith(AndroidJUnit4::class)
class NativeJourneyTest {
    @get:Rule val compose=createAndroidComposeRule<ComponentActivity>()
    private val viewModels=ViewModelStore()
    private lateinit var database:PersonalDatabase
    private lateinit var vm:PlatformViewModel
    @Volatile private var offline=false
    @Before fun setUp(){
        val app=ApplicationProvider.getApplicationContext<Context>()
        val context=object:ContextWrapper(app){override fun getSharedPreferences(name:String,mode:Int)=super.getSharedPreferences("qa_journey_"+name,mode)}
        database=Room.inMemoryDatabaseBuilder(context,PersonalDatabase::class.java).build()
        val meta=Meta(source="Synthetic QA fixture")
        val stock=Stock("NSE:FIXTURE","TEST FIXTURE Stock",match=true,match_type="exact",freshness="unavailable")
        val ipo=IPO("fixture-ipo","TEST FIXTURE Native IPO",type="SME",phase="ongoing",issue=Issue(price_band="₹90 – ₹100"))
        val sector=Sector("fixture","Fixture sector",1,1,0,0,0,0,stocks=listOf(stock))
        val overview=Overview(Health("disconnected","unavailable","closed"),"TEST FIXTURE session",buildJsonObject{put("exact",1)},listOf(sector),listOf(stock),listOf(ipo),buildJsonObject{put("label","Insufficient data")},meta)
        val proxy=Proxy.newProxyInstance(DivineApi::class.java.classLoader,arrayOf(DivineApi::class.java)){_,method,_->
            when(method.name){
                "ipos"->IPOPage(listOf(ipo),1,1,20,mapOf("ongoing" to 1),meta)
                "ipo"->IPODetail(ipo=ipo,meta=meta)
                "resource"->Resource(meta=meta.copy(unavailable=true))
                "watchlist"->Watchlist(emptyList(),"2026-11-03T00:00:00Z")
                "alerts"->AlertRules(emptyList())
                "inbox"->AlertInbox(emptyList())
                "preferences"->Preferences()
                "toString"->"FixtureApi"
                else->error("Unexpected fixture API call: "+method.name)
            }
        } as DivineApi
        val api=object:DivineApi by proxy {override suspend fun overview():Overview {if(offline)throw IOException("QA offline");return overview}}
        val sessions=SessionStore(context).apply{clear()}
        val repository=PlatformRepository(api,sessions,database.personal(),PreferencesStore(context),AuthenticatedCall(api,sessions))
        val factory=object:ViewModelProvider.Factory {@Suppress("UNCHECKED_CAST") override fun <T:ViewModel> create(modelClass:Class<T>):T=PlatformViewModel(repository) as T}
        vm=ViewModelProvider(viewModels,factory)[PlatformViewModel::class.java]
        compose.setContent {DivineApp(vm,MutableStateFlow(null)) {}}
        vm.refresh();compose.waitUntil(5000){vm.state.value.overview!=null}
    }
    @After fun tearDown(){viewModels.clear();database.close()}
    @Test fun ipoDetailsAndAndroidBackReturnToTheSameNavigationStack(){
        compose.onNodeWithText("IPO",useUnmergedTree=true).performClick()
        compose.waitUntil(5000){vm.state.value.ipos!=null}
        compose.onNodeWithText("TEST FIXTURE Native IPO",useUnmergedTree=true).performClick()
        compose.waitUntil(5000){vm.state.value.details.containsKey("fixture-ipo")}
        compose.onNodeWithText("FINANCIALS",useUnmergedTree=true).assertExists()
        compose.runOnUiThread {compose.activity.onBackPressedDispatcher.onBackPressed()}
        compose.onNodeWithText("Search IPOs",useUnmergedTree=true).assertIsDisplayed()
        compose.runOnUiThread {compose.activity.onBackPressedDispatcher.onBackPressed()}
        compose.onNodeWithText("Market overview",useUnmergedTree=true).assertIsDisplayed()
    }
    @Test fun offlineRefreshRetainsOnlyAnExplicitPreviousSnapshot(){
        offline=true;vm.refresh();compose.waitUntil(5000){vm.state.value.error!=null}
        compose.onNodeWithText("Offline. Reconnect to refresh data.",useUnmergedTree=true).assertIsDisplayed()
        compose.onNodeWithText("Previous snapshot",substring=true,useUnmergedTree=true).assertIsDisplayed()
    }
}
