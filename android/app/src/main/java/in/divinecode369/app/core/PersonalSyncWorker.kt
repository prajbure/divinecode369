package `in`.divinecode369.app.core

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import androidx.work.*
import dagger.hilt.EntryPoint
import dagger.hilt.InstallIn
import dagger.hilt.android.EntryPointAccessors
import dagger.hilt.components.SingletonComponent
import `in`.divinecode369.app.R
import `in`.divinecode369.app.data.PlatformRepository
import `in`.divinecode369.app.data.SeenEvent
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.first
import java.util.concurrent.TimeUnit

@EntryPoint @InstallIn(SingletonComponent::class)
interface WorkerDependencies { fun repository():PlatformRepository }

/** User-owned synchronization and the backend event inbox; no provider polling. */
class PersonalSyncWorker(context:Context,params:WorkerParameters):CoroutineWorker(context,params) {
    override suspend fun doWork():Result {
        val repository=EntryPointAccessors.fromApplication(applicationContext,WorkerDependencies::class.java).repository()
        if(!repository.sessions.signedIn.value)return Result.success()
        return try {
            repository.sync()
            val preferences=repository.preferences.values.first()
            val events=repository.account { repository.api.inbox() }.items
            val permitted=Build.VERSION.SDK_INT<33||ContextCompat.checkSelfPermission(applicationContext,Manifest.permission.POST_NOTIFICATIONS)==PackageManager.PERMISSION_GRANTED
            val manager=applicationContext.getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(NotificationChannel("ipo_dates","IPO watchlist",NotificationManager.IMPORTANCE_DEFAULT))
            for(event in events) if(!repository.local.seen(event.id)) {
                if(preferences.notifications&&permitted) {
                    val intent=android.content.Intent(applicationContext,`in`.divinecode369.app.MainActivity::class.java).apply { data=android.net.Uri.parse(if(event.kind=="stock")"https://divinecode369.in/stocks/"+android.net.Uri.encode(event.symbol?.substringAfter(':')?:"") else "https://divinecode369.in/ipo/details/"+event.ipo_slug) }
                    val pending=android.app.PendingIntent.getActivity(applicationContext,event.id.hashCode(),intent,android.app.PendingIntent.FLAG_IMMUTABLE or android.app.PendingIntent.FLAG_UPDATE_CURRENT)
                    manager.notify(event.id.hashCode(),NotificationCompat.Builder(applicationContext,"ipo_dates").setSmallIcon(R.drawable.ic_brand).setContentTitle("DIVINE CODE 369").setContentText(event.title).setContentIntent(pending).setAutoCancel(true).build())
                }
                repository.local.seen(SeenEvent(event.id))
            }
            Result.success()
        } catch(e:CancellationException) { throw e } catch(_:Exception) { if(runAttemptCount<3)Result.retry()else Result.failure() }
    }
    companion object {
        fun schedule(context:Context) {
            val work=PeriodicWorkRequestBuilder<PersonalSyncWorker>(15,TimeUnit.MINUTES).setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()).setBackoffCriteria(BackoffPolicy.EXPONENTIAL,30,TimeUnit.SECONDS).build()
            WorkManager.getInstance(context).enqueueUniquePeriodicWork("personal_sync",ExistingPeriodicWorkPolicy.KEEP,work)
        }
    }
}
