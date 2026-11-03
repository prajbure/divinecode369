@file:OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
package `in`.divinecode369.app.ui

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.browser.customtabs.CustomTabsIntent
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.*
import androidx.compose.foundation.lazy.grid.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material.icons.automirrored.rounded.ShowChart
import androidx.compose.material.icons.rounded.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavType
import androidx.navigation.compose.*
import androidx.navigation.navArgument
import coil.compose.AsyncImage
import `in`.divinecode369.app.BuildConfig
import `in`.divinecode369.app.data.api.*
import kotlinx.coroutines.flow.StateFlow
import kotlinx.serialization.json.*
import java.text.NumberFormat
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

private data class Destination(val route:String,val label:String,val icon:ImageVector)
private val destinations=listOf(Destination("home","HOME",Icons.Rounded.Home),Destination("scanner","SCANNER",Icons.Rounded.Radar),Destination("market","MARKET",Icons.AutoMirrored.Rounded.ShowChart),Destination("ipo","IPO",Icons.Rounded.BusinessCenter),Destination("more","MORE",Icons.Rounded.Apps))
fun amount(value:Double?,suffix:String="",currency:Boolean=false):String = value?.takeIf { it.isFinite() }?.let { (if(currency)"₹"else "")+NumberFormat.getNumberInstance(Locale.forLanguageTag("en-IN")).apply { maximumFractionDigits=2 }.format(it)+suffix }?:"—"
fun time(value:String?):String = try { OffsetDateTime.parse(value).atZoneSameInstant(ZoneId.of("Asia/Kolkata")).format(DateTimeFormatter.ofPattern("dd MMM HH:mm 'IST'")) }catch(_:Exception){"Time unavailable"}
fun JsonElement?.text():String?=(this as? JsonPrimitive)?.contentOrNull
fun JsonElement?.number():Double?=(this as? JsonPrimitive)?.doubleOrNull
private fun open(context:Context,url:String) {
    val uri=Uri.parse(url)
    if(uri.scheme=="https"&&!uri.host.isNullOrBlank()&&uri.userInfo==null)runCatching { CustomTabsIntent.Builder().setShowTitle(true).build().launchUrl(context,uri) }
}
private fun share(context:Context,title:String,url:String) { context.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).apply { type="text/plain";putExtra(Intent.EXTRA_TEXT,"$title\n$url") },"Share IPO")) }

@Composable fun DivineApp(vm:PlatformViewModel,links:StateFlow<String?>,consumeLink:()->Unit) {
    val state by vm.state.collectAsStateWithLifecycle();val prefs by vm.preferences.collectAsStateWithLifecycle()
    val signedIn by vm.signedIn.collectAsStateWithLifecycle();val link by links.collectAsStateWithLifecycle()
    val nav=rememberNavController();val entry by nav.currentBackStackEntryAsState();val route=entry?.destination?.route?:"home"
    val snackbar=remember { SnackbarHostState() };val context=LocalContext.current
    LaunchedEffect(state.message){state.message?.let { snackbar.showSnackbar(it);vm.consumeMessage() }}
    LaunchedEffect(link){link?.let {
        val uri=Uri.parse(it)
        if(uri.scheme=="https"&&uri.host=="divinecode369.in") {
            val parts=uri.pathSegments
            if(parts.size==3&&parts[0]=="ipo"&&parts[1]=="details"&&parts[2].matches(Regex("[a-z0-9]+(?:-[a-z0-9]+)*")))nav.navigate("ipoDetail/"+Uri.encode(parts[2]))
            if(parts.size==2&&parts[0]=="stocks")nav.navigate("stock/"+Uri.encode(parts[1]))
        };consumeLink()
    }}
    CompositionLocalProvider(LocalPresentationDensity provides prefs.density) { DivineTheme(prefs.theme) {
        BoxWithConstraints(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {
            val tablet=maxWidth>=720.dp
            Row(Modifier.fillMaxSize()) {
                fun go(destination:Destination) {nav.navigate(destination.route){popUpTo(nav.graph.findStartDestination().id){saveState=true};launchSingleTop=true;restoreState=true}}
                if(tablet)NavigationRail(Modifier.fillMaxHeight().navigationBarsPadding()) {
                    Spacer(Modifier.height(90.dp));destinations.forEach { d->NavigationRailItem(selected=route==d.route,onClick={go(d)},icon={Icon(d.icon,d.label)},label={Text(d.label,fontSize=10.sp)}) }
                }
                Scaffold(modifier=Modifier.weight(1f),topBar={
                    TopAppBar(title={Column { Text("DIVINE CODE 369",fontWeight=FontWeight.Bold,fontSize=18.sp);Text(if(route.startsWith("ipo"))"IPO INTELLIGENCE"else "MARKET INTELLIGENCE",fontSize=10.sp,color=MaterialTheme.colorScheme.primary) }},
                        navigationIcon={if(route !in destinations.map{it.route})IconButton(onClick={nav.popBackStack()}){Icon(Icons.AutoMirrored.Rounded.ArrowBack,"Back")}},
                        actions={IconButton(onClick={nav.navigate("alerts")}){Icon(Icons.Rounded.NotificationsNone,"Alerts")};IconButton(onClick={nav.navigate(if(signedIn)"settings"else "login")}){Icon(if(signedIn)Icons.Rounded.AccountCircle else Icons.Rounded.PersonOutline,"Account")}})
                },bottomBar={if(!tablet)NavigationBar {
                    destinations.forEach { d->NavigationBarItem(selected=route==d.route,onClick={go(d)},icon={Icon(d.icon,d.label)},label={Text(d.label,fontSize=10.sp)},alwaysShowLabel=true) }
                }},snackbarHost={SnackbarHost(snackbar)}) { padding->
                    Column(Modifier.padding(padding).fillMaxSize()) {
                        if(state.loading)LinearProgressIndicator(Modifier.fillMaxWidth())
                        state.error?.let { ErrorStrip(it){vm.refresh()} }
                        if(state.overview!=null&&(state.error!=null||System.currentTimeMillis()-state.refreshedAt>60_000))Text("Previous snapshot · ${time(state.overview?.meta?.provider_timestamp)}",Modifier.fillMaxWidth().padding(horizontal=18.dp,vertical=6.dp),fontSize=11.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)
                        NavHost(navController=nav,startDestination="home",modifier=Modifier.weight(1f)) {
                            composable("home"){HomeScreen(state,{nav.navigate(it)},vm)}
                            composable("scanner"){ScannerScreen(state.overview?.sectors?:emptyList(),{nav.navigate("stock/"+Uri.encode(it))})}
                            composable("market"){MarketScreen(state.overview?.sectors?:emptyList(),tablet){nav.navigate("sector/"+Uri.encode(it))}}
                            composable("ipo"){IpoScreen(state,vm){nav.navigate(it)}}
                            composable("more"){MoreScreen(signedIn){nav.navigate(it)}}
                            composable("sector/{id}",arguments=listOf(navArgument("id"){type=NavType.StringType})){back->
                                val sector=state.overview?.sectors?.find { it.id==back.arguments?.getString("id") }
                                StockList(sector?.name?:"Sector",sector?.stocks?:emptyList()){nav.navigate("stock/"+Uri.encode(it))}
                            }
                            composable("stock/{symbol}",arguments=listOf(navArgument("symbol"){type=NavType.StringType})){back->
                                val symbol=back.arguments?.getString("symbol")?:"";val row=state.overview?.sectors?.flatMap{it.stocks}?.find{it.symbol==symbol||it.symbol=="NSE:$symbol"}
                                StockScreen(row,vm){nav.navigate("history/"+Uri.encode(it))}
                            }
                            composable("ipoDetail/{slug}",arguments=listOf(navArgument("slug"){type=NavType.StringType})){back->IpoDetailScreen(back.arguments?.getString("slug")?:"",state,vm)}
                            composable("watchlist"){WatchlistScreen(vm){nav.navigate(it)}}
                            composable("alerts"){AlertsScreen(vm,state,signedIn){nav.navigate(it)}}
                            composable("settings"){SettingsScreen(vm,signedIn){nav.navigate(it)}}
                            composable("login"){LoginScreen(vm,state,signedIn){nav.popBackStack()}}
                            composable("health"){HealthScreen(state.overview?.health)}
                            composable("ai"){LaunchedEffect(Unit){if(signedIn)vm.predictions()};Page("AI Predictions"){item{Text("Research only · training remains disabled",color=MaterialTheme.colorScheme.onSurfaceVariant)};item{if(!signedIn)Button(onClick={nav.navigate("login")}){Text("Sign in")}else JsonFacts(state.predictions)}}}
                            composable("history"){HistoryPicker(state.overview?.sectors?:emptyList()){nav.navigate("history/"+Uri.encode(it))}}
                            composable("history/{symbol}",arguments=listOf(navArgument("symbol"){type=NavType.StringType})){back->
                                val symbol=back.arguments?.getString("symbol")?:"";LaunchedEffect(symbol){if(signedIn)vm.history(symbol)}
                                Page("History · $symbol"){item{if(!signedIn)Button(onClick={nav.navigate("login")}){Text("Sign in")}else if(state.history?.enabled!=true)Empty("Licensed historical retention is not enabled.")else JsonFacts(JsonArray(state.history?.candles?:emptyList()))}}
                            }
                        }
                    }
                }
            }
        }
    }
}}

@Composable fun Page(title:String,content:LazyListScope.()->Unit) {
    val spacing=when(LocalPresentationDensity.current){"compact"->10.dp;"large"->20.dp;else->14.dp}
    LazyColumn(Modifier.fillMaxSize(),contentPadding=PaddingValues(horizontal=18.dp,vertical=16.dp),verticalArrangement=Arrangement.spacedBy(spacing)) {
        item("title"){Text(title,style=MaterialTheme.typography.headlineLarge)};content();item("bottom"){Spacer(Modifier.height(12.dp))}
    }
}
@Composable fun Panel(modifier:Modifier=Modifier,content:@Composable ColumnScope.()->Unit) { val padding=when(LocalPresentationDensity.current){"compact"->12.dp;"large"->22.dp;else->16.dp};Surface(modifier.fillMaxWidth(),shape=RoundedCornerShape(18.dp),color=MaterialTheme.colorScheme.surface,border=BorderStroke(1.dp,MaterialTheme.colorScheme.outline.copy(alpha=.55f))){Column(Modifier.padding(padding),verticalArrangement=Arrangement.spacedBy(10.dp),content=content)} }
@Composable fun Empty(label:String="Unavailable"){Panel {Text(label,color=MaterialTheme.colorScheme.onSurfaceVariant)} }
@Composable fun ErrorStrip(message:String,retry:()->Unit){Row(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.errorContainer).padding(horizontal=12.dp),verticalAlignment=Alignment.CenterVertically){Text(message,Modifier.weight(1f),fontSize=12.sp);TextButton(onClick=retry){Text("Retry")}}}
@Composable fun Metric(label:String,value:String,modifier:Modifier=Modifier,color:Color=MaterialTheme.colorScheme.onSurface){Column(modifier,verticalArrangement=Arrangement.spacedBy(5.dp)){Text(label,fontSize=11.sp,color=MaterialTheme.colorScheme.onSurfaceVariant);Text(value,fontSize=17.sp,fontWeight=FontWeight.SemiBold,color=color)} }
@Composable fun Movement(value:Double?){Text(amount(value,"%"),color=if(value==null)MaterialTheme.colorScheme.onSurfaceVariant else if(value>=0)Gain else Loss,fontWeight=FontWeight.SemiBold)}
@Composable fun SectionTitle(title:String,action:String?=null,onClick:()->Unit={}) {Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.CenterVertically){Text(title,Modifier.weight(1f),style=MaterialTheme.typography.titleLarge);if(action!=null)TextButton(onClick=onClick){Text(action)}}}
@Composable private fun HomeScreen(state:PlatformState,navigate:(String)->Unit,vm:PlatformViewModel) {
    val overview=state.overview
    Page("Market overview") {
        item { Text(overview?.market_label?:"Waiting for backend",color=MaterialTheme.colorScheme.onSurfaceVariant,fontSize=12.sp) }
        item {Panel {Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){Metric("Exact",overview?.summary?.get("exact").text()?:"—",color=Cyan);Metric("Near",overview?.summary?.get("near").text()?:"—");Metric("Live",overview?.health?.live?.toString()?:"—")};Text(time(overview?.meta?.provider_timestamp),fontSize=11.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)}}
        item {SectionTitle("Opening matches","Scanner"){navigate("scanner")}}
        if(overview?.matches.isNullOrEmpty())item {Empty("No verified opening matches.")}
        items(overview?.matches?.take(5)?:emptyList(),key={"match:"+it.symbol}){StockCard(it){navigate("stock/"+Uri.encode(it.symbol))}}
        item {SectionTitle("Sector highlights","All 16"){navigate("market")}}
        items(overview?.sectors?.sortedByDescending{it.strength?:-1.0}?.take(4)?:emptyList(),key={"sector:"+it.id}){sector->SectorCard(sector){navigate("sector/"+sector.id)}}
        item {SectionTitle("Market regime")}
        item {Panel {Text(overview?.regime?.get("label").text()?:"Unavailable");Text("Custom basket observations · not investment advice",fontSize=11.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)}}
        item {SectionTitle("Connection health","Details"){navigate("health")}}
        item {HealthCompact(overview?.health)}
        item {Text("Developed by ER PRAJWAL AMBURE",fontSize=10.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)}
    }
}

@Composable fun StockCard(stock:Stock,onClick:()->Unit) {
    Panel(Modifier.clickable(onClick=onClick)) {
        Row(verticalAlignment=Alignment.CenterVertically){Column(Modifier.weight(1f)){Text(stock.symbol.substringAfter(':'),fontWeight=FontWeight.Bold,color=if(stock.match)Cyan else MaterialTheme.colorScheme.onSurface);Text(stock.sectors.joinToString(" · "),fontSize=10.sp,color=MaterialTheme.colorScheme.onSurfaceVariant,maxLines=1,overflow=TextOverflow.Ellipsis)};Column(horizontalAlignment=Alignment.End){Text(amount(stock.ltp,currency=true),fontWeight=FontWeight.Bold);Movement(stock.change_pct)}}
        Row(horizontalArrangement=Arrangement.spacedBy(16.dp)){Metric("Prev close",amount(stock.prev_close),Modifier.weight(1f));Metric("Open",amount(stock.open),Modifier.weight(1f));Metric("Difference",stock.difference_display?:"—",Modifier.weight(1f),if(stock.match)Cyan else MaterialTheme.colorScheme.onSurface)}
        Text("${stock.match_type.uppercase()} · ${stock.freshness} · ${time(stock.provider_timestamp)}",fontSize=10.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)
    }
}
@Composable private fun ScannerScreen(sectors:List<Sector>,onStock:(String)->Unit) {
    var query by rememberSaveable{mutableStateOf("")};var match by rememberSaveable{mutableStateOf("all")};var sector by rememberSaveable{mutableStateOf("all")};var sorting by rememberSaveable{mutableStateOf("symbol")};var expanded by remember{mutableStateOf(false)}
    val rows=remember(sectors,query,match,sector,sorting){
        val filtered=sectors.flatMap{it.stocks}.distinctBy{it.symbol}.filter{r->(sector=="all"||sector in r.sector_ids)&&(query.isBlank()||(r.symbol+" "+r.name).contains(query,true))&&when(match){"exact"->r.match;"near"->r.near_match;"all"->r.match||r.near_match;else->true}}
        when(sorting){"difference"->filtered.sortedBy{it.difference?.let{v->kotlin.math.abs(v)}?:Double.MAX_VALUE};"change"->filtered.sortedByDescending{it.change_pct?:-Double.MAX_VALUE};"relevance"->filtered.sortedByDescending{it.opportunity["score"].number()?:-1.0};else->filtered.sortedBy{it.symbol}}
    }
    Page("Opening scanner") {
        item {OutlinedTextField(query,{query=it},Modifier.fillMaxWidth(),singleLine=true,label={Text("Search stocks")},leadingIcon={Icon(Icons.Rounded.Search,null)})}
        item {Row(Modifier.horizontalScroll(rememberScrollState()),horizontalArrangement=Arrangement.spacedBy(8.dp)){listOf("all" to "All Matches","exact" to "Exact","near" to "Near","universe" to "Universe").forEach{(key,label)->FilterChip(selected=match==key,onClick={match=key},label={Text(label)})}}}
        item {Row(horizontalArrangement=Arrangement.spacedBy(8.dp)){Box(Modifier.weight(1f)){OutlinedButton(onClick={expanded=true}){Text(sectors.find{it.id==sector}?.name?:"All sectors",maxLines=1)};DropdownMenu(expanded,{expanded=false}){DropdownMenuItem(text={Text("All sectors")},onClick={sector="all";expanded=false});sectors.forEach{s->DropdownMenuItem(text={Text(s.name)},onClick={sector=s.id;expanded=false})}}};SortMenu(sorting){sorting=it}}}
        item {Text("${rows.size} instruments",fontSize=12.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)}
        if(rows.isEmpty())item{Empty("No verified results for these filters.")}
        items(rows,key={it.symbol}){StockCard(it){onStock(it.symbol)}}
    }
}
@Composable private fun SortMenu(value:String,select:(String)->Unit){var expanded by remember{mutableStateOf(false)};Box {OutlinedButton(onClick={expanded=true}){Icon(Icons.Rounded.Sort,null);Text(value.replaceFirstChar{it.uppercase()})};DropdownMenu(expanded,{expanded=false}){listOf("symbol","difference","change","relevance").forEach{key->DropdownMenuItem(text={Text(key.replaceFirstChar{it.uppercase()})},onClick={select(key);expanded=false})}}}}
@Composable private fun SectorCard(sector:Sector,onClick:()->Unit){Panel(Modifier.clickable(onClick=onClick)){Row {Text(sector.name,Modifier.weight(1f),style=MaterialTheme.typography.titleMedium);Movement(sector.average)};Row(horizontalArrangement=Arrangement.SpaceBetween,modifier=Modifier.fillMaxWidth()){Metric("Strength",amount(sector.strength,"/100"));Metric("Adv / Dec","${sector.advancing} / ${sector.declining}");Metric("Coverage","${sector.available}/${sector.unique_symbols}")}}}
@Composable private fun MarketScreen(sectors:List<Sector>,tablet:Boolean,onSector:(String)->Unit){Column(Modifier.fillMaxSize().padding(horizontal=18.dp)){Text("Sector market",style=MaterialTheme.typography.headlineLarge,modifier=Modifier.padding(vertical=16.dp));Text("16 sectors · 160 memberships",fontSize=12.sp,color=MaterialTheme.colorScheme.onSurfaceVariant);LazyVerticalGrid(columns=GridCells.Fixed(if(tablet)2 else 1),verticalArrangement=Arrangement.spacedBy(12.dp),horizontalArrangement=Arrangement.spacedBy(12.dp),contentPadding=PaddingValues(vertical=16.dp)){items(sectors,key={it.id}){SectorCard(it){onSector(it.id)}}}}}
@Composable private fun StockList(title:String,rows:List<Stock>,onStock:(String)->Unit){Page(title){if(rows.isEmpty())item{Empty("Waiting for backend")};items(rows,key={it.symbol}){StockCard(it){onStock(it.symbol)}}}}
@Composable private fun StockScreen(stock:Stock?,vm:PlatformViewModel,history:(String)->Unit){val saved by vm.saved.collectAsStateWithLifecycle();var alertDialog by remember{mutableStateOf(false)};val platform by vm.state.collectAsStateWithLifecycle();Page(stock?.name?:"Stock"){if(stock==null)item{Empty("Quote unavailable")}else{
    item {StockCard(stock){}}
    item {Row(horizontalArrangement=Arrangement.spacedBy(10.dp)){OutlinedButton(onClick={vm.toggle("stock",stock.symbol,stock.name)}){Icon(if(saved.any{it.kind=="stock"&&it.key==stock.symbol&&it.saved})Icons.Rounded.Bookmark else Icons.Rounded.BookmarkBorder,null);Text("Watch")};OutlinedButton(onClick={history(stock.symbol)}){Text("History")};OutlinedButton(onClick={alertDialog=true}){Icon(Icons.Rounded.NotificationsNone,"Market alert")}}}
    item{SectionTitle("Opening intelligence")};item{JsonFacts(stock.intelligence)};item{OutlinedButton(onClick={vm.context(stock.symbol)}){Text("Load authorized stored context")}};platform.contexts[stock.symbol]?.let{context->item{JsonFacts((context["opening"] as? JsonObject)?.get(stock.symbol))}}
    item{SectionTitle("Opportunity Radar")};item{JsonFacts(stock.opportunity)}
    item{Text("Rule relevance, not a probability of profit. No orders are executed.",fontSize=11.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)}
}};if(alertDialog&&stock!=null)MarketAlertDialog(stock.symbol,{alertDialog=false}){event,threshold->vm.saveMarketAlert(stock.symbol,event,threshold);alertDialog=false}}

@Composable private fun MoreScreen(signedIn:Boolean,navigate:(String)->Unit){val context=LocalContext.current;Page("More"){
    items(listOf("ai" to "AI Predictions","history" to "History","watchlist" to "Watchlists","alerts" to "Alerts","health" to "Connection health","settings" to "Settings","login" to if(signedIn)"Connected account"else "Sign in"),key={it.first}){(path,title)->Panel(Modifier.clickable{navigate(path)}){Row {Text(title,Modifier.weight(1f));Icon(Icons.Rounded.ChevronRight,null)}}}
    item{OutlinedButton(onClick={open(context,"https://divinecode369.in/settings")},modifier=Modifier.fillMaxWidth()){Icon(Icons.Rounded.AdminPanelSettings,null);Text("Owner connection manager")}}
    item{Text("Developed by ER PRAJWAL AMBURE",fontSize=11.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)}
}}
@Composable private fun HealthCompact(health:Health?){Panel {Text("Kite · ${health?.kite_state?:"unavailable"}");Text("IPO Guru · ${health?.ipo_state?:"unavailable"}");Text("${health?.live?:0} live · ${health?.stale?:0} stale",fontSize=12.sp,color=MaterialTheme.colorScheme.onSurfaceVariant);Text("${health?.unavailable?:148} unavailable · ${health?.unknown?:0} unknown · ${health?.closed?:0} closed",fontSize=11.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)}}
@Composable private fun HealthScreen(health:Health?){Page("Connection health"){item{HealthCompact(health)};item{Metric("Provider update",time(health?.provider_timestamp))};item{Metric("Backend refresh",time(health?.cache_timestamp))};item{Text(health?.notifications?:"Authenticated inbox",fontSize=12.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)}}}
@Composable private fun LoginScreen(vm:PlatformViewModel,state:PlatformState,signedIn:Boolean,back:()->Unit){val context=LocalContext.current;DisposableEffect(Unit){onDispose{vm.cancelSignIn()}};Page("Connect account"){
    if(signedIn)item{Panel{Text("Device connected",color=Gain);Text("Market · IPO · personal lists",fontSize=12.sp);Button(onClick=back){Text("Continue")}}}
    else {
        item{Text("Approve this device in your owner browser.",color=MaterialTheme.colorScheme.onSurfaceVariant)}
        state.device?.let{device->item{Panel{Text(device.user_code,style=MaterialTheme.typography.headlineLarge,color=Cyan);Text("Check this code on the approval page.",fontSize=12.sp);Button(onClick={val uri=Uri.parse(device.verification_uri);if(uri.scheme=="https"&&uri.host=="divinecode369.in")open(context,device.verification_uri)}){Text("Open secure approval")};Text("Waiting for owner approval…",fontSize=12.sp)}}}
        item{Button(onClick=vm::signIn,enabled=!state.deviceBusy){Text(if(state.deviceBusy)"Starting…"else if(state.device!=null)"Start again"else "Connect device")}}
        item{Text("Provider and administrator secrets stay on the server.",fontSize=11.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)}
    }
}}
@Composable private fun WatchlistScreen(vm:PlatformViewModel,navigate:(String)->Unit){val saved by vm.saved.collectAsStateWithLifecycle();val signedIn by vm.signedIn.collectAsStateWithLifecycle();Page("Watchlists"){
    item{Text(if(signedIn)"Synced with your website account"else "Saved on this device · sign in to sync",fontSize=12.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)}
    if(saved.none{it.saved})item{Empty("Save a stock or IPO to begin.")}
    items(saved.filter{it.saved},key={it.kind+":"+it.key}){item->Panel{Row(verticalAlignment=Alignment.CenterVertically){Column(Modifier.weight(1f).clickable{navigate((if(item.kind=="ipo")"ipoDetail/"else "stock/")+Uri.encode(item.key))}){Text(item.label,fontWeight=FontWeight.SemiBold);Text(item.kind.uppercase()+if(item.dirty)" · pending sync"else "",fontSize=10.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)};IconButton(onClick={vm.toggle(item.kind,item.key,item.label)}){Icon(Icons.Rounded.BookmarkRemove,"Remove saved item")}}}}
    if(!signedIn)item{Button(onClick={navigate("login")}){Text("Sign in to sync")}}
}}
@Composable private fun AlertsScreen(vm:PlatformViewModel,state:PlatformState,signedIn:Boolean,navigate:(String)->Unit){val alerts by vm.alerts.collectAsStateWithLifecycle();LaunchedEffect(signedIn){if(signedIn)vm.inbox()};Page("Alerts"){
    item{Text("Backend inbox · device delivery follows Android background limits",fontSize=12.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)}
    if(!signedIn)item{Button(onClick={navigate("login")}){Text("Sign in to sync alerts")}}
    item{SectionTitle("Your rules")};if(alerts.isEmpty())item{Empty("Add alerts from stock or IPO details.")}
    items(alerts,key={it.id}){rule->Panel {Row(verticalAlignment=Alignment.CenterVertically){Column(Modifier.weight(1f)){Text(rule.slug);Text(rule.event.replace('_',' ')+(rule.threshold?.let{" ≥ "+amount(it)}?:""),fontSize=12.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)};IconButton(onClick={vm.removeAlert(rule)}){Icon(Icons.Rounded.DeleteOutline,"Delete alert")}}}}
    item{SectionTitle("Inbox")};if(state.inbox.isEmpty())item{Empty("No backend events yet.")};items(state.inbox,key={it.id}){event->Panel(Modifier.clickable{navigate(if(event.kind=="stock")"stock/"+Uri.encode(event.symbol?:"")else "ipoDetail/"+Uri.encode(event.ipo_slug))}){Text(event.title);Text(time(event.created_at),fontSize=11.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)}}
}}
@Composable private fun SettingsScreen(vm:PlatformViewModel,signedIn:Boolean,navigate:(String)->Unit){val prefs by vm.preferences.collectAsStateWithLifecycle();val context=LocalContext.current
    val permission=rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()){granted->vm.savePreferences(prefs.copy(notifications=granted))}
    Page("Settings"){
        item{SectionTitle("Appearance")};item{Panel {Text("Theme");Row(Modifier.horizontalScroll(rememberScrollState()),horizontalArrangement=Arrangement.spacedBy(8.dp)){listOf("dark","light","system").forEach{key->FilterChip(prefs.theme==key,{vm.savePreferences(prefs.copy(theme=key))},label={Text(key.replaceFirstChar{it.uppercase()})})}};Text("Density");Row(Modifier.horizontalScroll(rememberScrollState()),horizontalArrangement=Arrangement.spacedBy(8.dp)){listOf("compact","comfortable","large").forEach{key->FilterChip(prefs.density==key,{vm.savePreferences(prefs.copy(density=key))},label={Text(key.replaceFirstChar{it.uppercase()})})}}}}
        item{Panel {Row(verticalAlignment=Alignment.CenterVertically){Text("IPO notifications",Modifier.weight(1f));Switch(prefs.notifications,{enabled->if(enabled&&Build.VERSION.SDK_INT>=33&&ContextCompat.checkSelfPermission(context,Manifest.permission.POST_NOTIFICATIONS)!=PackageManager.PERMISSION_GRANTED)permission.launch(Manifest.permission.POST_NOTIFICATIONS)else vm.savePreferences(prefs.copy(notifications=enabled))})};Text("Opt-in inbox notifications; FCM is not configured.",fontSize=11.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)}}
        item{Panel {Text(if(signedIn)"Account connected"else "Account offline");if(signedIn){OutlinedButton(onClick={vm.sync()}){Text("Sync account")};OutlinedButton(onClick={vm.logout()}){Text("Sign out")}}else Button(onClick={navigate("login")}){Text("Sign in")}}}
        item{OutlinedButton(onClick={navigate("alerts")}){Text("Market & IPO alerts")}}
        item{OutlinedButton(onClick={navigate("health")}){Text("Advanced · data health")}}
        item{TextButton(onClick={open(context,"https://divinecode369.in/privacy")}){Text("Privacy")}}
        item{Text("Version ${BuildConfig.VERSION_NAME} (${BuildConfig.VERSION_CODE})",fontSize=12.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)}
    }
}
@Composable private fun HistoryPicker(sectors:List<Sector>,onStock:(String)->Unit){var query by rememberSaveable{mutableStateOf("")};Page("Price history"){item{OutlinedTextField(query,{query=it},label={Text("Search stocks")},modifier=Modifier.fillMaxWidth())};items(sectors.flatMap{it.stocks}.distinctBy{it.symbol}.filter{it.symbol.contains(query,true)||it.name.contains(query,true)},key={it.symbol}){stock->ListItem(headlineContent={Text(stock.name)},supportingContent={Text(stock.symbol)},modifier=Modifier.clickable{onStock(stock.symbol)})}}}

@Composable fun JsonFacts(value:JsonElement?,depth:Int=0) {
    when(value) {
        null,JsonNull->Empty()
        is JsonPrimitive->Text(value.contentOrNull?:"—",color=MaterialTheme.colorScheme.onSurfaceVariant,fontSize=13.sp)
        is JsonArray->Column(verticalArrangement=Arrangement.spacedBy(10.dp)){if(value.isEmpty())Text("Unavailable",color=MaterialTheme.colorScheme.onSurfaceVariant);value.take(100).forEach{JsonFacts(it,depth+1)}}
        is JsonObject->Column(verticalArrangement=Arrangement.spacedBy(10.dp)){
            value.entries.filter{it.value!=JsonNull}.take(60).forEach{(label,entry)->
                if(entry is JsonPrimitive)Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){Text(label.replace('_',' ').replaceFirstChar{it.uppercase()},Modifier.weight(1f),fontSize=12.sp,color=MaterialTheme.colorScheme.onSurfaceVariant);Text(entry.content.take(160),Modifier.weight(1f),fontSize=12.sp)}
                else if(depth<4){var expanded by rememberSaveable(label){mutableStateOf(false)};TextButton(onClick={expanded=!expanded}){Text(label.replace('_',' ').replaceFirstChar{it.uppercase()}+if(expanded)" −"else " +")};if(expanded)JsonFacts(entry,depth+1)}
            }
        }
    }
}
