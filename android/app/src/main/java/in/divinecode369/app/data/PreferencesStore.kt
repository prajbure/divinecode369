package `in`.divinecode369.app.data

import android.content.Context
import androidx.datastore.preferences.core.*
import androidx.datastore.preferences.preferencesDataStore
import dagger.hilt.android.qualifiers.ApplicationContext
import `in`.divinecode369.app.data.api.Preferences
import kotlinx.coroutines.flow.map
import javax.inject.Inject
import javax.inject.Singleton

private val Context.preferences by preferencesDataStore("display_preferences")
@Singleton class PreferencesStore @Inject constructor(@ApplicationContext private val context:Context) {
    private val theme=stringPreferencesKey("theme");private val density=stringPreferencesKey("density");private val notifications=booleanPreferencesKey("notifications");private val dirty=booleanPreferencesKey("dirty")
    val values=context.preferences.data.map { Preferences(it[theme]?:"dark",it[density]?:"comfortable",it[notifications]?:false) }
    val needsSync=context.preferences.data.map { it[dirty]?:false }
    suspend fun save(value:Preferences,pending:Boolean=true) { context.preferences.edit { it[theme]=value.theme;it[density]=value.density;it[notifications]=value.notifications;it[dirty]=pending } }
}
