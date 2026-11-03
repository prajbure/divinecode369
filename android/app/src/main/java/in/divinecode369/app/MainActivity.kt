package `in`.divinecode369.app

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import dagger.hilt.android.AndroidEntryPoint
import `in`.divinecode369.app.core.PersonalSyncWorker
import `in`.divinecode369.app.ui.DivineApp
import `in`.divinecode369.app.ui.PlatformViewModel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.launch

@AndroidEntryPoint
class MainActivity:ComponentActivity() {
    private val model:PlatformViewModel by viewModels()
    private val links=MutableStateFlow<String?>(null)
    override fun onCreate(savedInstanceState:Bundle?) {
        installSplashScreen();super.onCreate(savedInstanceState);enableEdgeToEdge();links.value=intent?.dataString
        setContent { DivineApp(model,links) { links.value=null } }
        PersonalSyncWorker.schedule(this)
        lifecycleScope.launch { repeatOnLifecycle(Lifecycle.State.STARTED) {
            model.refresh(sync=true)
            while(true){delay(20_000);model.refresh()}
        } }
    }
    override fun onNewIntent(intent:Intent){super.onNewIntent(intent);setIntent(intent);links.value=intent.dataString}
}
