package `in`.divinecode369.app.data

import android.content.Context
import androidx.room.*
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import kotlinx.coroutines.flow.Flow
import javax.inject.Singleton

@Entity(tableName="saved",primaryKeys=["kind","key"])
data class SavedEntity(val kind:String,val key:String,val label:String,val saved:Boolean,val dirty:Boolean=true,val revision:Long=System.currentTimeMillis())
@Entity(tableName="alert_rules")
data class AlertEntity(@PrimaryKey val id:String,val slug:String,val event:String,val threshold:Double?,val enabled:Boolean,val dirty:Boolean=true,val deleted:Boolean=false,val kind:String="ipo")
@Entity(tableName="seen_events") data class SeenEvent(@PrimaryKey val id:String)
@Dao interface PersonalDao {
    @Query("SELECT * FROM saved ORDER BY revision DESC") fun observeSaved():Flow<List<SavedEntity>>
    @Query("SELECT * FROM saved") suspend fun saved():List<SavedEntity>
    @Upsert suspend fun save(item:SavedEntity)
    @Query("UPDATE saved SET dirty=0 WHERE kind=:kind AND `key`=:key AND revision=:revision") suspend fun markSynced(kind:String,key:String,revision:Long)
    @Query("SELECT * FROM alert_rules WHERE deleted=0") fun observeAlerts():Flow<List<AlertEntity>>
    @Query("SELECT * FROM alert_rules") suspend fun alerts():List<AlertEntity>
    @Upsert suspend fun save(rule:AlertEntity)
    @Query("DELETE FROM alert_rules WHERE id=:id") suspend fun removeAlert(id:String)
    @Query("SELECT EXISTS(SELECT 1 FROM seen_events WHERE id=:id)") suspend fun seen(id:String):Boolean
    @Insert(onConflict=OnConflictStrategy.IGNORE) suspend fun seen(event:SeenEvent)
}
@Database(entities=[SavedEntity::class,AlertEntity::class,SeenEvent::class],version=1,exportSchema=true)
abstract class PersonalDatabase:RoomDatabase() { abstract fun personal():PersonalDao }
@Module @InstallIn(SingletonComponent::class) object LocalModule {
    @Provides @Singleton fun database(@ApplicationContext context:Context):PersonalDatabase = Room.databaseBuilder(context,PersonalDatabase::class.java,"personal.sqlite3").build()
    @Provides fun dao(db:PersonalDatabase)=db.personal()
}
