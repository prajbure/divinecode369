package `in`.divinecode369.app.ui

import android.os.Build
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import `in`.divinecode369.app.core.DeviceProof
import `in`.divinecode369.app.core.readableError
import `in`.divinecode369.app.data.*
import `in`.divinecode369.app.data.api.*
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import kotlinx.serialization.json.JsonObject
import retrofit2.HttpException
import java.util.UUID
import javax.inject.Inject

data class PlatformState(val overview:Overview?=null,val loading:Boolean=false,val error:String?=null,val refreshedAt:Long=0,
    val ipos:IPOPage?=null,val ipoLoading:Boolean=false,val ipoError:String?=null,val phase:String="ongoing",val board:String="all",val query:String="",
    val details:Map<String,IPODetail> = emptyMap(),val resources:Map<String,Resource> = emptyMap(),val detailError:String?=null,
    val device:DeviceStarted?=null,val deviceBusy:Boolean=false,val message:String?=null,val inbox:List<AlertEvent> = emptyList(),val history:History?=null,val predictions:JsonObject?=null,val contexts:Map<String,JsonObject> = emptyMap())

@HiltViewModel class PlatformViewModel @Inject constructor(val repository:PlatformRepository):ViewModel() {
    private val _state=MutableStateFlow(PlatformState());val state=_state.asStateFlow()
    val signedIn=repository.sessions.signedIn
    val saved=repository.local.observeSaved().stateIn(viewModelScope,SharingStarted.WhileSubscribed(5000),emptyList())
    val alerts=repository.local.observeAlerts().stateIn(viewModelScope,SharingStarted.WhileSubscribed(5000),emptyList())
    val preferences=repository.preferences.values.stateIn(viewModelScope,SharingStarted.WhileSubscribed(5000),Preferences())
    private var refreshing=false;private var ipoJob:Job?=null;private var loginJob:Job?=null
    fun refresh(sync:Boolean=false) { if(refreshing)return;viewModelScope.launch {
        refreshing=true;_state.update { it.copy(loading=true) }
        try { val overview=repository.api.overview();val ipoChanged=state.value.ipos?.let{it.meta.cache_timestamp!=overview.health.ipo_cache_timestamp}?:false;_state.update { it.copy(overview=overview,error=null,refreshedAt=System.currentTimeMillis()) };if(ipoChanged)loadIpos();if(sync&&signedIn.value)sync() }
        catch(e:CancellationException){throw e}catch(e:Exception){_state.update { it.copy(error=readableError(e)) }}
        finally { refreshing=false;_state.update { it.copy(loading=false) } }
    } }
    fun filterIpos(phase:String=state.value.phase,board:String=state.value.board,query:String=state.value.query) {
        _state.update { it.copy(phase=phase,board=board,query=query) };loadIpos()
    }
    fun loadIpos(more:Boolean=false) {
        if(more&&state.value.ipoLoading)return
        ipoJob?.cancel();ipoJob=viewModelScope.launch {
            if(!more)delay(300)
            val before=state.value;_state.update { it.copy(ipoLoading=true,ipoError=null) }
            try {
                val page=repository.api.ipos(before.phase,before.board,before.query,if(more)(before.ipos?.page?:0)+1 else 1)
                _state.update { it.copy(ipos=if(more)page.copy(items=((before.ipos?.items?:emptyList())+page.items).distinctBy { ipo->ipo.slug })else page) }
            }catch(e:CancellationException){throw e}catch(e:Exception){_state.update { it.copy(ipoError=readableError(e)) }}
            finally{_state.update { it.copy(ipoLoading=false) }}
        }
    }
    fun detail(slug:String,force:Boolean=false) { if(!force&&state.value.details.containsKey(slug))return;viewModelScope.launch {
        _state.update { it.copy(detailError=null) }
        try { val value=repository.api.ipo(slug);_state.update { it.copy(details=it.details+(slug to value)) } }
        catch(e:CancellationException){throw e}catch(e:Exception){_state.update { it.copy(detailError=readableError(e)) }}
    } }
    fun resource(slug:String,kind:String) {val key="$slug/$kind";if(state.value.resources.containsKey(key))return;viewModelScope.launch {
        try { val value=repository.api.resource(slug,kind);_state.update { it.copy(resources=it.resources+(key to value)) } }
        catch(e:CancellationException){throw e}catch(e:Exception){_state.update { it.copy(detailError=readableError(e)) }}
    } }
    fun toggle(kind:String,key:String,label:String)=task { repository.toggle(kind,key,label);if(signedIn.value)repository.sync() }
    fun sync()=task { repository.sync();_state.update { it.copy(message="Account synced") } }
    fun savePreferences(value:Preferences)=task { repository.preferences.save(value);if(signedIn.value)repository.sync() }
    fun saveAlert(slug:String,event:String,threshold:Double?=null)=task {
        repository.local.save(AlertEntity(UUID.randomUUID().toString(),slug,event,threshold,true));if(signedIn.value)repository.sync();_state.update { it.copy(message="Alert saved") }
    }
    fun saveMarketAlert(symbol:String,event:String,threshold:Double?=null)=task {
        repository.local.save(AlertEntity(UUID.randomUUID().toString(),symbol,event,threshold,true,kind="stock"));if(signedIn.value)repository.sync();_state.update { it.copy(message="Market alert saved") }
    }
    fun removeAlert(rule:AlertEntity)=task { repository.local.save(rule.copy(deleted=true,dirty=true));if(signedIn.value)repository.sync() }
    fun inbox()=task { val items=repository.account { repository.api.inbox() }.items;_state.update { it.copy(inbox=items) } }
    fun history(symbol:String)=task {val value=repository.account { repository.api.history(symbol) };_state.update { it.copy(history=value) } }
    fun predictions()=task {val value=repository.account { repository.api.predictions() };_state.update { it.copy(predictions=value) } }
    fun context(symbol:String)=task {val value=repository.account { repository.api.intelligence(symbol) };_state.update { it.copy(contexts=it.contexts+(symbol to value)) } }
    fun logout()=task { repository.signOut();_state.update { it.copy(message="Signed out") } }
    fun consumeMessage(){_state.update { it.copy(message=null) }}
    fun signIn() {
        loginJob?.cancel();loginJob=viewModelScope.launch {
            _state.update { it.copy(deviceBusy=true,device=null) }
            try {
                val verifier=DeviceProof.verifier()
                val device=repository.api.start(DeviceStart("${Build.MANUFACTURER} ${Build.MODEL}".take(80),DeviceProof.challenge(verifier)))
                _state.update { it.copy(device=device,deviceBusy=false) }
                val deadline=System.currentTimeMillis()+device.expires_in*1000L
                while(System.currentTimeMillis()<deadline) {
                    delay(maxOf(5,device.interval)*1000L)
                    try {
                        val tokens=repository.api.token(DeviceGrant(device.request_id,verifier));repository.sessions.save(tokens)
                        _state.update { it.copy(device=null,message="Device connected") };repository.sync();return@launch
                    }catch(e:HttpException){if(e.code() !in listOf(428,429))throw e}
                }
                _state.update { it.copy(device=null,message="Device request expired. Start again.") }
            }catch(e:CancellationException){throw e}catch(e:Exception){_state.update { it.copy(message=readableError(e)) }}
            finally{_state.update { it.copy(deviceBusy=false) }}
        }
    }
    fun cancelSignIn(){loginJob?.cancel();_state.update { it.copy(device=null,deviceBusy=false) }}
    private fun task(block:suspend()->Unit)=viewModelScope.launch {
        try{block()}catch(e:CancellationException){throw e}catch(e:Exception){_state.update { it.copy(message=readableError(e)) }}
    }
}
