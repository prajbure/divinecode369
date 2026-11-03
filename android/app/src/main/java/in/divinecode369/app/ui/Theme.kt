package `in`.divinecode369.app.ui

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

val Cyan=Color(0xFF00D9FF);val Gain=Color(0xFF23CC97);val Loss=Color(0xFFFF687C);val Midnight=Color(0xFF080F20)
val LocalPresentationDensity=staticCompositionLocalOf { "comfortable" }
private val Dark=darkColorScheme(primary=Cyan,onPrimary=Midnight,secondary=Color(0xFF8FAAFF),tertiary=Color(0xFFB09AF7),background=Midnight,surface=Color(0xFF101B30),surfaceVariant=Color(0xFF17243B),onSurface=Color(0xFFF2F5FC),onSurfaceVariant=Color(0xFF9EADC5),outline=Color(0xFF293B55),error=Loss)
private val Light=lightColorScheme(primary=Color(0xFF006D86),secondary=Color(0xFF315DAC),background=Color(0xFFF3F6FC),surface=Color.White,surfaceVariant=Color(0xFFE6ECF6),onSurface=Color(0xFF0E1C31),onSurfaceVariant=Color(0xFF51617A))
@Composable fun DivineTheme(theme:String="dark",content: @Composable () -> Unit) {
    val dark=theme=="dark"||(theme=="system"&&isSystemInDarkTheme())
    MaterialTheme(colorScheme=if(dark)Dark else Light,typography=Typography(
        headlineLarge=TextStyle(fontFamily=FontFamily.SansSerif,fontSize=30.sp,fontWeight=FontWeight.Bold),
        titleLarge=TextStyle(fontSize=21.sp,fontWeight=FontWeight.SemiBold),titleMedium=TextStyle(fontSize=16.sp,fontWeight=FontWeight.SemiBold),
        bodyMedium=TextStyle(fontSize=14.sp),labelSmall=TextStyle(fontSize=11.sp,fontWeight=FontWeight.Medium)),content=content)
}
