package `in`.divinecode369.app.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.sp

@Composable fun MarketAlertDialog(symbol:String,dismiss:()->Unit,save:(String,Double?)->Unit) {
    var event by rememberSaveable{mutableStateOf("exact")};var threshold by rememberSaveable{mutableStateOf("")}
    val price=event in listOf("price_above","price_below");val number=threshold.toDoubleOrNull()?.takeIf{it.isFinite()&&it in 0.0..1_000_000.0}
    AlertDialog(onDismissRequest=dismiss,title={Text("Market alert")},text={Column {
        Text(symbol,fontSize=12.sp)
        listOf("exact" to "Exact opening match","near" to "Near opening match","price_above" to "Price reaches above ₹","price_below" to "Price reaches below ₹").forEach{(key,label)->Row(Modifier.fillMaxWidth().clickable{event=key},verticalAlignment=Alignment.CenterVertically){RadioButton(event==key,{event=key});Text(label,fontSize=13.sp)}}
        if(price)OutlinedTextField(threshold,{threshold=it},label={Text("Price ₹")},singleLine=true)
        Text("Fresh verified quotes only. Background delivery can be delayed by Android.",fontSize=11.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)
    }},confirmButton={TextButton(onClick={save(event,number)},enabled=!price||number!=null){Text("Save alert")}},dismissButton={TextButton(onClick=dismiss){Text("Cancel")}})
}
