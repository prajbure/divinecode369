@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
package `in`.divinecode369.app.ui

import android.content.Intent
import android.net.Uri
import androidx.browser.customtabs.CustomTabsIntent
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import coil.compose.AsyncImage
import `in`.divinecode369.app.data.api.*
import kotlinx.serialization.json.*
import java.time.LocalDate
import java.time.ZoneId

private val phases=listOf("ongoing","upcoming","allotted","closed")
@Composable fun IpoScreen(state:PlatformState,vm:PlatformViewModel,navigate:(String)->Unit) {
    val saved by vm.saved.collectAsStateWithLifecycle();var query by rememberSaveable{mutableStateOf(state.query)}
    LaunchedEffect(Unit){vm.loadIpos()}
    Column(Modifier.fillMaxSize()) {
        Row(Modifier.padding(horizontal=18.dp),verticalAlignment=Alignment.CenterVertically){Text("IPO Intelligence",Modifier.weight(1f),style=MaterialTheme.typography.titleLarge);IconButton(onClick={navigate("watchlist")}){Icon(Icons.Rounded.BookmarkBorder,"Watchlist")};IconButton(onClick={vm.loadIpos()}){Icon(Icons.Rounded.Refresh,"Refresh IPOs")}}
        OutlinedTextField(query,{query=it;vm.filterIpos(query=it)},Modifier.fillMaxWidth().padding(horizontal=18.dp),label={Text("Search IPOs")},singleLine=true,leadingIcon={Icon(Icons.Rounded.Search,null)})
        SecondaryScrollableTabRow(selectedTabIndex=phases.indexOf(state.phase).coerceAtLeast(0),edgePadding=10.dp) {
            phases.forEach{phase->Tab(selected=phase==state.phase,onClick={vm.filterIpos(phase=phase)},text={Text(phase.uppercase(),fontSize=11.sp)})}
        }
        Row(Modifier.padding(horizontal=18.dp).horizontalScroll(rememberScrollState()),horizontalArrangement=Arrangement.spacedBy(8.dp)) {
            listOf("all" to "ALL","Mainboard" to "MAINBOARD","SME" to "SME").forEach{(key,label)->FilterChip(selected=state.board==key,onClick={vm.filterIpos(board=key)},label={Text(label,fontSize=11.sp)})}
        }
        if(state.ipoLoading)LinearProgressIndicator(Modifier.fillMaxWidth())
        state.ipoError?.let { ErrorStrip(it){vm.loadIpos()} }
        val page=state.ipos
        LazyColumn(contentPadding=PaddingValues(18.dp),verticalArrangement=Arrangement.spacedBy(12.dp),modifier=Modifier.weight(1f)) {
            item("freshness"){Text(if(page?.meta?.unavailable==true)"IPO Guru unavailable"else "${page?.total?:0} IPOs · ${if(page?.meta?.stale==true)"stale cache"else "shared cache"} · ${time(page?.meta?.cache_timestamp)}",fontSize=10.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)}
            if(page?.items.isNullOrEmpty()&&!state.ipoLoading)item("empty"){Empty(if(page?.meta?.unavailable==true)page.meta.message?:"IPO data unavailable"else "No IPOs in this view.")}
            items(page?.items?:emptyList(),key={it.slug}){ipo->IpoCard(ipo,saved.any{it.kind=="ipo"&&it.key==ipo.slug&&it.saved},{vm.toggle("ipo",ipo.slug,ipo.name)}){navigate("ipoDetail/"+Uri.encode(ipo.slug))}}
            if(page!=null&&page.items.size<page.total)item("more"){OutlinedButton(onClick={vm.loadIpos(more=true)},enabled=!state.ipoLoading,modifier=Modifier.fillMaxWidth()){Text("Load more")}}
            item("disclaimer"){Text("GMP is unofficial and does not guarantee listing returns. Data by IPO Guru.",fontSize=10.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)}
        }
    }
}

fun ipoDateLabel(ipo:IPO):String {
    val today=LocalDate.now(ZoneId.of("Asia/Kolkata")).toString();val tomorrow=LocalDate.now(ZoneId.of("Asia/Kolkata")).plusDays(1).toString()
    return when(ipo.phase){
        "ongoing"->when(ipo.timeline.close_date){today->"Closes today";tomorrow->"Closes tomorrow";null->"Close date unavailable";else->"Closes ${ipo.timeline.close_date}"}
        "upcoming"->ipo.timeline.open_date?.let{"Opens $it"}?:"Dates to be announced"
        "allotted"->"Allotment confirmed"
        else->if(ipo.is_listed)"Listed ${ipo.timeline.listing_date?:""}"else "Closed ${ipo.timeline.close_date?:""}"
    }
}
@Composable fun IpoCard(ipo:IPO,saved:Boolean,onSave:()->Unit,onOpen:()->Unit) {
    val context=LocalContext.current
    Panel(Modifier.clickable(onClick=onOpen)) {
        Row(verticalAlignment=Alignment.CenterVertically) {
            if(ipo.logo!=null)AsyncImage(ipo.logo,ipo.name,modifier=Modifier.size(42.dp).background(MaterialTheme.colorScheme.surfaceVariant,RoundedCornerShape(10.dp)))
            else Box(Modifier.size(42.dp).background(MaterialTheme.colorScheme.surfaceVariant,RoundedCornerShape(10.dp)),contentAlignment=Alignment.Center){Text(ipo.name.take(1),fontWeight=FontWeight.Bold,color=Cyan)}
            Spacer(Modifier.width(10.dp));Column(Modifier.weight(1f)){Text(ipo.name,fontWeight=FontWeight.SemiBold,maxLines=2,overflow=TextOverflow.Ellipsis,fontSize=15.sp);Text("${ipo.issue.listing_on?:"Exchange —"} · ${ipo.type}",fontSize=10.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)}
            IconButton(onClick=onSave,modifier=Modifier.size(40.dp)){Icon(if(saved)Icons.Rounded.Bookmark else Icons.Rounded.BookmarkAdd,if(saved)"Remove from watchlist"else "Save IPO",tint=if(saved)Cyan else MaterialTheme.colorScheme.onSurfaceVariant)}
            IconButton(onClick={context.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).apply{type="text/plain";putExtra(Intent.EXTRA_TEXT,"${ipo.name}\nhttps://divinecode369.in/ipo/details/${ipo.slug}")},"Share IPO"))},modifier=Modifier.size(40.dp)){Icon(Icons.Rounded.Share,"Share IPO")}
        }
        Text(ipoDateLabel(ipo),fontSize=11.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)
        HorizontalDivider(color=MaterialTheme.colorScheme.outline.copy(alpha=.4f))
        Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.spacedBy(10.dp)) {
            Metric("Issue price",ipo.issue.price_band?:amount(ipo.issue.issue_price,currency=true),Modifier.weight(1.2f))
            Column(Modifier.weight(1f),verticalArrangement=Arrangement.spacedBy(4.dp)){Text("GMP",fontSize=11.sp,color=MaterialTheme.colorScheme.onSurfaceVariant);Text(amount(ipo.gmp.price,currency=true),fontWeight=FontWeight.SemiBold,color=if((ipo.gmp.price?:0.0)>=0)Gain else Loss);Text(amount(ipo.gmp.percentage,"%"),fontSize=11.sp,color=if((ipo.gmp.percentage?:0.0)>=0)Gain else Loss)}
            Metric("Subscription",amount(ipo.subscription_total,"×"),Modifier.weight(1f))
        }
        Text("GMP · ${ipo.gmp.freshness.status} · ${time(ipo.gmp.freshness.as_of)}",fontSize=9.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable fun IpoDetailScreen(slug:String,state:PlatformState,vm:PlatformViewModel) {
    var tab by rememberSaveable(slug){mutableIntStateOf(0)};var showAlerts by remember{mutableStateOf(false)}
    val detail=state.details[slug];val ipo=detail?.ipo;val saved by vm.saved.collectAsStateWithLifecycle();val context=LocalContext.current
    LaunchedEffect(slug){vm.detail(slug)}
    LaunchedEffect(slug,tab){if(tab==1)vm.resource(slug,"history");if(tab==2)vm.resource(slug,"subscription");if(tab==6)vm.resource(slug,"listing-comparison")}
    Column(Modifier.fillMaxSize()) {
        Row(Modifier.padding(horizontal=18.dp),verticalAlignment=Alignment.CenterVertically){Text(ipo?.name?:"IPO details",Modifier.weight(1f),style=MaterialTheme.typography.titleLarge,maxLines=2);IconButton(onClick={if(ipo!=null)vm.toggle("ipo",slug,ipo.name)}){Icon(if(saved.any{it.kind=="ipo"&&it.key==slug&&it.saved})Icons.Rounded.Bookmark else Icons.Rounded.BookmarkBorder,"Watch IPO")};IconButton(onClick={showAlerts=true}){Icon(Icons.Rounded.NotificationsActive,"Configure IPO alerts")};IconButton(onClick={vm.detail(slug,true)}){Icon(Icons.Rounded.Refresh,"Refresh details")}}
        SecondaryScrollableTabRow(selectedTabIndex=tab,edgePadding=12.dp){listOf("OVERVIEW","GMP","SUBSCRIPTION","FINANCIALS","TIMELINE","ALLOTMENT","LISTING").forEachIndexed{i,label->Tab(selected=tab==i,onClick={tab=i},text={Text(label,fontSize=11.sp)})}}
        state.detailError?.let{ErrorStrip(it){vm.detail(slug,true)}}
        LazyColumn(Modifier.weight(1f),contentPadding=PaddingValues(18.dp),verticalArrangement=Arrangement.spacedBy(16.dp)) {
            if(detail==null)item{Empty("Loading provider data…")}
            else if(ipo==null)item{Empty(detail.meta.message?:"Provider detail unavailable")}
            else {
                item{Text("${ipo.type} · ${ipo.issue.listing_on?:"Exchange —"} · ${if(detail.meta.stale)"stale cache"else "shared cache"}",fontSize=11.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)}
                when(tab) {
                    0->{
                        item{Panel {Facts(listOf("Issue type" to ipo.issue.sale_type,"Price band" to (ipo.issue.price_band?:amount(ipo.issue.issue_price,currency=true)),"Lot size" to amount(ipo.issue.lot_size),"Minimum investment" to amount(ipo.issue.min_investment,currency=true),"Issue size" to amount(ipo.issue.issue_size),"Exchange" to ipo.issue.listing_on))}}
                        item{SectionTitle("Company")};item{ExpandableText(detail.company["about"].text()?:detail.company["description"].text())}
                        item{SectionTitle("Important dates")};item{TimelineView(ipo.timeline)}
                        item{SectionTitle("Research & risks")};item{JsonFacts(buildJsonObject{detail.company["strengths"]?.let{put("strengths",it)};detail.company["risks"]?.let{put("risks",it)};detail.company["objects_of_issue"]?.let{put("objects_of_issue",it)}})}
                    }
                    1->{
                        item{Panel {Row(horizontalArrangement=Arrangement.SpaceBetween,modifier=Modifier.fillMaxWidth()){Metric("Latest GMP",amount(ipo.gmp.price,currency=true),color=Gain);Metric("GMP %",amount(ipo.gmp.percentage,"%"));Metric("Est. listing",amount(ipo.gmp.estimate,currency=true))};Text("${ipo.gmp.freshness.status} · ${time(ipo.gmp.freshness.as_of)}",fontSize=11.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)}}
                        item{Text("Unofficial GMP. Estimated listing is arithmetic, not a forecast or guaranteed return.",fontSize=11.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)}
                        val history=state.resources["$slug/history"]
                        item{SectionTitle("Day-wise GMP")};item{GmpChart(history?.data?.get("trend") as? JsonArray)}
                        item{history?.meta?.message?.let{Text(it,fontSize=12.sp)}}
                    }
                    2->{val resource=state.resources["$slug/subscription"];val data=resource?.data
                        item{Text(time((data?.get("freshness") as? JsonObject)?.get("as_of").text()),fontSize=11.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)}
                        val categories=(data?.get("categories") as? JsonArray)?.mapNotNull{it as? JsonObject}?:emptyList()
                        if(categories.isEmpty())item{Empty(resource?.meta?.message?:"Subscription categories unavailable")}
                        items(categories,key={it["key"].text()?:it.toString()}){category->Panel {Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){Text(category["label"].text()?:category["key"].text()?:"Category");Text(amount(category["times"].number(),"×"),fontWeight=FontWeight.Bold,color=Cyan)};JsonFacts(category["sub_categories"])}}
                    }
                    3->{val financials=detail.company["financials"] as? JsonObject
                        item{Text(financials?.get("unit").text()?:"Provider units unavailable",fontSize=12.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)}
                        val headers=(financials?.get("headers") as? JsonArray)?.map{it.text()?:"—"}?:emptyList()
                        val rows=(financials?.get("rows") as? JsonArray)?.mapNotNull{it as? JsonObject}?:emptyList()
                        if(rows.isEmpty())item{Empty("Financials unavailable from this provider plan.")}
                        items(rows){row->Panel {Text(row["metric"].text()?:"Metric",fontWeight=FontWeight.SemiBold);(row["data"] as? JsonArray)?.forEachIndexed{i,value->Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){Text(headers.getOrNull(i)?:"Period —",fontSize=12.sp,color=MaterialTheme.colorScheme.onSurfaceVariant);Text(value.text()?:"—",fontSize=13.sp)}}}}
                        item{SectionTitle("Valuation & ratios")};item{JsonFacts(detail.company["kpis"])}
                    }
                    4->item{TimelineView(ipo.timeline)}
                    5->{
                        item{Panel {Metric("Expected allotment",ipo.timeline.allotment_date?:"Unavailable");Text(if(detail.allotment_confirmed)"Basis of allotment published"else "Expected date is not confirmation.",fontSize=12.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)
                            detail.registrar["name"]?.let{Text(it)}
                            detail.registrar["url"]?.let{url->OutlinedButton(onClick={val uri=Uri.parse(url);if(uri.scheme=="https"&&uri.userInfo==null)CustomTabsIntent.Builder().build().launchUrl(context,uri)}){Text("Official registrar ↗")}}?:Text("Registrar link unavailable",fontSize=12.sp)
                            OutlinedButton(onClick={vm.toggle("ipo",slug,ipo.name)}){Text("Track in watchlist")}
                        }}
                    }
                    6->item{Panel {Facts(listOf("Issue price" to amount(ipo.issue.issue_price,currency=true),"Actual listing price" to amount(ipo.listing.price,currency=true),"Listing gain / loss" to amount(ipo.listing.gain,"%"),"Current listed price" to amount(ipo.listing.cmp,currency=true)));JsonFacts(state.resources["$slug/listing-comparison"]?.data);Text(time(ipo.listing.freshness.as_of),fontSize=11.sp)}}
                }
                item{Text("Data by IPO Guru · Personal research · ${time(detail.meta.cache_timestamp)}",fontSize=10.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)}
            }
        }
    }
    if(showAlerts)IpoAlertDialog(slug,{showAlerts=false}){event,threshold->vm.saveAlert(slug,event,threshold);showAlerts=false}
}
@Composable private fun Facts(rows:List<Pair<String,String?>>){Column(verticalArrangement=Arrangement.spacedBy(14.dp)){rows.forEach{(label,value)->Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){Text(label,Modifier.weight(1f),fontSize=12.sp,color=MaterialTheme.colorScheme.onSurfaceVariant);Text(value?:"—",Modifier.weight(1f),fontSize=13.sp)}}}}
@Composable private fun TimelineView(timeline:Timeline){Panel {Facts(listOf("IPO opens" to timeline.open_date,"IPO closes" to timeline.close_date,"Allotment" to timeline.allotment_date,"Refund / unblocking" to timeline.refund_date,"Demat credit" to timeline.credit_to_demat_date,"Listing" to timeline.listing_date))}}
@Composable private fun ExpandableText(value:String?){var expanded by rememberSaveable{mutableStateOf(false)};if(value==null)Empty()else Column {Text(value,maxLines=if(expanded)Int.MAX_VALUE else 4,overflow=TextOverflow.Ellipsis,fontSize=13.sp,color=MaterialTheme.colorScheme.onSurfaceVariant);TextButton(onClick={expanded=!expanded}){Text(if(expanded)"Less"else "Company details")}}}
@Composable private fun GmpChart(trend:JsonArray?) {
    val points=trend?.mapNotNull{row->(row as? JsonObject)?.let{entry->entry["price"].number()?.let{(entry["date"].text()?:"—") to it}}}?:emptyList()
    if(points.isEmpty()){Empty("Day-wise GMP unavailable");return}
    Panel {
        Canvas(Modifier.fillMaxWidth().height(140.dp)) {
            val low=points.minOf{it.second};val high=points.maxOf{it.second};val span=(high-low).takeIf{it>0}?:1.0
            val coords=points.mapIndexed{i,p->Offset(if(points.size==1)size.width/2 else i.toFloat()/(points.size-1)*size.width,(size.height-(p.second-low)/span*size.height).toFloat())}
            val path=Path();coords.forEachIndexed{i,p->if(i==0)path.moveTo(p.x,p.y)else path.lineTo(p.x,p.y)}
            drawPath(path,Cyan,style=Stroke(width=3.dp.toPx()));coords.forEach{drawCircle(Cyan,3.dp.toPx(),it)}
        }
        Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){Text(points.first().first,fontSize=10.sp);Text(points.last().first,fontSize=10.sp)}
        points.takeLast(7).forEach{(date,price)->Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){Text(date,fontSize=12.sp,color=MaterialTheme.colorScheme.onSurfaceVariant);Text(amount(price,currency=true),fontSize=12.sp)}}
    }
}
@Composable private fun IpoAlertDialog(slug:String,dismiss:()->Unit,save:(String,Double?)->Unit){var event by rememberSaveable{mutableStateOf("opens")};var threshold by rememberSaveable{mutableStateOf("")}
    val options=listOf("opens" to "IPO opens","closes_tomorrow" to "Closes tomorrow","gmp_threshold" to "GMP reaches amount","gmp_change" to "GMP changes by amount","subscription_threshold" to "Subscription reaches multiple","allotment" to "Allotment date","listing" to "Listing day")
    val needsThreshold=(event.endsWith("_threshold")||event=="gmp_change");val number=threshold.toDoubleOrNull()?.takeIf{it.isFinite()&&it in 0.0..1_000_000.0}
    AlertDialog(onDismissRequest=dismiss,title={Text("IPO alert")},text={Column(Modifier.verticalScroll(rememberScrollState())){Text(slug,fontSize=11.sp);options.forEach{(key,label)->Row(Modifier.fillMaxWidth().clickable{event=key},verticalAlignment=Alignment.CenterVertically){RadioButton(event==key,{event=key});Text(label,fontSize=13.sp)}};if(needsThreshold)OutlinedTextField(threshold,{threshold=it},label={Text(if(event in listOf("gmp_threshold","gmp_change"))"Amount ₹"else "Subscription ×")},singleLine=true);Text("Threshold alerts need a fresh, verified source update. Delivery uses the backend inbox.",fontSize=11.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)}},confirmButton={TextButton(onClick={save(event,number)},enabled=!needsThreshold||number!=null){Text("Save alert")}},dismissButton={TextButton(onClick=dismiss){Text("Cancel")}})
}
