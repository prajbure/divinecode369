package `in`.divinecode369.app

import androidx.compose.runtime.*
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import `in`.divinecode369.app.data.api.IPO
import `in`.divinecode369.app.data.api.Issue
import `in`.divinecode369.app.ui.DivineTheme
import `in`.divinecode369.app.ui.IpoCard
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class NativeCardTest {
    @get:Rule val compose=createComposeRule()
    @Test fun providerCardSupportsWatchAndDetailActionsWithUnavailableNumbers() {
        var opened=false
        compose.setContent {var saved by remember{mutableStateOf(false)};DivineTheme {IpoCard(IPO(slug="fixture-ipo",name="TEST FIXTURE Native IPO",type="SME",issue=Issue(price_band="₹90 – ₹100")),saved,{saved=!saved}){opened=true}}}
        compose.onNodeWithText("TEST FIXTURE Native IPO",useUnmergedTree=true).assertIsDisplayed()
        compose.onNodeWithText("₹90 – ₹100",useUnmergedTree=true).assertIsDisplayed()
        compose.onNodeWithContentDescription("Save IPO").performClick()
        compose.onNodeWithContentDescription("Remove from watchlist").assertExists()
        compose.onNodeWithText("TEST FIXTURE Native IPO",useUnmergedTree=true).performClick()
        compose.runOnIdle {assertTrue(opened)}
    }
}
