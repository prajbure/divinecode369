package `in`.divinecode369.app.data

import `in`.divinecode369.app.core.AuthenticatedCall
import `in`.divinecode369.app.core.SessionStore
import `in`.divinecode369.app.data.api.*
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import javax.inject.Inject
import javax.inject.Singleton

@Singleton class PlatformRepository @Inject constructor(
    val api:DivineApi, val sessions:SessionStore, val local:PersonalDao,
    val preferences:PreferencesStore, private val authenticated:AuthenticatedCall
) {
    private val syncLock=Mutex()
    suspend fun <T> account(block:suspend()->T):T=authenticated.run(block)
    suspend fun toggle(kind:String,key:String,label:String) {
        val old=local.saved().find { it.kind==kind&&it.key==key }
        local.save(SavedEntity(kind,key,label,old?.saved!=true))
    }
    suspend fun sync()=syncLock.withLock {
        if(!sessions.signedIn.value)return@withLock
        for(item in local.saved().filter { it.dirty }) {
            account { api.save(SavedItem(item.kind,item.key,item.label,item.saved)) }
            local.markSynced(item.kind,item.key,item.revision)
        }
        val remote=account { api.watchlist() }
        for(item in remote.items) {
            val existing=local.saved().find { it.kind==item.kind&&it.key==item.key }
            if(existing?.dirty!=true) local.save(SavedEntity(item.kind,item.key,item.label,item.saved,false,existing?.revision?:System.currentTimeMillis()))
        }
        for(rule in local.alerts().filter { it.dirty }) {
            if(rule.deleted) { account { api.deleteAlert(rule.id) };local.save(rule.copy(dirty=false)) }
            else { account { api.saveAlert(AlertRule(id=rule.id,ipo_slug=if(rule.kind=="ipo")rule.slug else "",event=rule.event,threshold=rule.threshold,enabled=rule.enabled,kind=rule.kind,symbol=if(rule.kind=="stock")rule.slug else null)) };local.save(rule.copy(dirty=false)) }
        }
        for(rule in account { api.alerts() }.items) {
            if(local.alerts().none { it.id==rule.id&&it.dirty }) local.save(AlertEntity(rule.id,if(rule.kind=="stock")rule.symbol?:""else rule.ipo_slug,rule.event,rule.threshold,rule.enabled,false,rule.deleted,rule.kind))
        }
        if(preferences.needsSync.first()) {
            val current=preferences.values.first()
            account { api.preferences(current) }
            if(preferences.values.first()==current)preferences.save(current,pending=false)
        }
        if(!preferences.needsSync.first()) {
            val remotePreferences=account { api.preferences() }
            if(!preferences.needsSync.first())preferences.save(remotePreferences,pending=false)
        }
    }
    suspend fun signOut() {
        try { account { api.logout() } } finally { sessions.clear() }
    }
}
