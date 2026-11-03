package `in`.divinecode369.app

import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import `in`.divinecode369.app.data.*
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.util.UUID

@RunWith(AndroidJUnit4::class)
class PersonalStorageTest {
    @Test fun userOwnedRecordsAndDeletionSurviveDatabaseReopen()=runBlocking {
        val context=ApplicationProvider.getApplicationContext<android.content.Context>()
        val name="qa-personal-${UUID.randomUUID()}.sqlite3"
        var db=Room.databaseBuilder(context,PersonalDatabase::class.java,name).build()
        try {
            db.personal().save(SavedEntity("ipo","fixture-ipo","Fixture IPO",true))
            db.personal().save(AlertEntity("fixture-rule","fixture-ipo","opens",null,true))
            db.close();db=Room.databaseBuilder(context,PersonalDatabase::class.java,name).build()
            assertTrue(db.personal().saved().single().saved)
            assertEquals("opens",db.personal().alerts().single().event)
            db.personal().save(db.personal().saved().single().copy(saved=false))
            db.close();db=Room.databaseBuilder(context,PersonalDatabase::class.java,name).build()
            assertFalse(db.personal().saved().single().saved)
        }finally {db.close();context.deleteDatabase(name)}
    }
}
