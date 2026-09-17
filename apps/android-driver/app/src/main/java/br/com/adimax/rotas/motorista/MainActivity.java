package br.com.adimax.rotas.motorista;

import android.Manifest;
import android.annotation.SuppressLint;
import android.app.Activity;
import android.app.AlertDialog;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.ActivityNotFoundException;
import android.content.ClipData;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.location.Location;
import android.location.LocationListener;
import android.location.LocationManager;
import android.net.Uri;
import android.os.Bundle;
import android.provider.MediaStore;
import android.provider.Settings;
import android.webkit.GeolocationPermissions;
import android.webkit.JavascriptInterface;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.RenderProcessGoneDetail;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;
import androidx.activity.OnBackPressedCallback;
import androidx.annotation.NonNull;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;
import androidx.core.content.FileProvider;
import androidx.core.app.NotificationCompat;
import androidx.core.graphics.Insets;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowInsetsCompat;
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import org.json.JSONObject;

public class MainActivity extends AppCompatActivity {
    private static final int LOCATION_PERMISSION=4101,CAMERA_PERMISSION=4102,FILE_CHOOSER=4103,INITIAL_PERMISSIONS=4104;
    private WebView webView; private SwipeRefreshLayout swipeRefresh; private ValueCallback<Uri[]> fileCallback;
    private Uri cameraOutput; private String pendingGeoOrigin; private GeolocationPermissions.Callback pendingGeoCallback;
    private LocationManager locationManager; private LocationListener locationListener; private boolean locationRequested=false; private long locationInterval=120000L; private File pendingInstallApk;

    @SuppressLint({"SetJavaScriptEnabled","JavascriptInterface"})
    @Override protected void onCreate(Bundle state){super.onCreate(state);setContentView(R.layout.activity_main);webView=findViewById(R.id.webView);swipeRefresh=findViewById(R.id.swipeRefresh);locationManager=(LocationManager)getSystemService(LOCATION_SERVICE);configureSafeArea();createOperationalNotificationChannel();
        WebSettings s=webView.getSettings();s.setJavaScriptEnabled(true);s.setDomStorageEnabled(true);s.setDatabaseEnabled(true);s.setGeolocationEnabled(true);s.setAllowFileAccess(false);s.setAllowContentAccess(true);s.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);s.setCacheMode(WebSettings.LOAD_DEFAULT);s.setUserAgentString(s.getUserAgentString()+" AdimaxMotorista/1.3 AndroidWebView");
        webView.addJavascriptInterface(new AndroidLocationBridge(),"AndroidLocation");webView.addJavascriptInterface(new AndroidNavigationBridge(),"AndroidNavigation");webView.setWebViewClient(new DriverWebViewClient());webView.setWebChromeClient(new DriverChromeClient());webView.setDownloadListener((url,a,d,t,z)->openExternal(url));
        // As rotas já são atualizadas por polling. O gesto de recarregar fechava a parada e os anexos em andamento.
        swipeRefresh.setEnabled(false);
        getOnBackPressedDispatcher().addCallback(this,new OnBackPressedCallback(true){@Override public void handleOnBackPressed(){if(webView.canGoBack())webView.goBack();else finish();}});
        if(state==null)webView.loadUrl(getSharedPreferences("driver_navigation",MODE_PRIVATE).getString("last_route_url",BuildConfig.APP_URL+"/routes"));else webView.restoreState(state);checkForUpdate();
    }
    private void configureSafeArea(){ViewCompat.setOnApplyWindowInsetsListener(swipeRefresh,(view,insets)->{Insets bars=insets.getInsets(WindowInsetsCompat.Type.systemBars()|WindowInsetsCompat.Type.displayCutout());view.setPadding(bars.left,bars.top,bars.right,bars.bottom);return insets;});ViewCompat.requestApplyInsets(swipeRefresh);}
    private void createOperationalNotificationChannel(){NotificationManager manager=getSystemService(NotificationManager.class);NotificationChannel channel=new NotificationChannel("adimax_operational_alerts","Avisos operacionais",NotificationManager.IMPORTANCE_HIGH);channel.setDescription("Alterações de rota, ocorrências e avisos ao motorista");channel.enableVibration(true);manager.createNotificationChannel(channel);}
    private void showOperationalNotification(String title,String message,int notificationId){Intent open=new Intent(this,MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP|Intent.FLAG_ACTIVITY_SINGLE_TOP);PendingIntent pending=PendingIntent.getActivity(this,notificationId,open,PendingIntent.FLAG_IMMUTABLE|PendingIntent.FLAG_UPDATE_CURRENT);android.app.Notification notification=new NotificationCompat.Builder(this,"adimax_operational_alerts").setSmallIcon(R.mipmap.ic_launcher).setContentTitle(title).setContentText(message).setStyle(new NotificationCompat.BigTextStyle().bigText(message)).setPriority(NotificationCompat.PRIORITY_HIGH).setAutoCancel(true).setContentIntent(pending).build();getSystemService(NotificationManager.class).notify(notificationId,notification);}
    @Override protected void onSaveInstanceState(@NonNull Bundle out){webView.saveState(out);super.onSaveInstanceState(out);}
    @Override protected void onPause(){saveNavigationUrl(webView.getUrl());super.onPause();}
    @Override protected void onResume(){super.onResume();if(locationRequested)startLocationUpdates(locationInterval);if(pendingInstallApk!=null&&pendingInstallApk.exists()&&(android.os.Build.VERSION.SDK_INT<26||getPackageManager().canRequestPackageInstalls())){File apk=pendingInstallApk;pendingInstallApk=null;webView.postDelayed(()->installUpdate(apk),350);}}
    @Override protected void onDestroy(){stopLocationUpdates();webView.removeJavascriptInterface("AndroidLocation");webView.removeJavascriptInterface("AndroidNavigation");webView.destroy();super.onDestroy();}
    private boolean isLocal(String h){return "10.0.2.2".equals(h)||"127.0.0.1".equals(h)||"localhost".equalsIgnoreCase(h);}
    private boolean internal(Uri u){Uri b=Uri.parse(BuildConfig.APP_URL);return u.getHost()!=null&&u.getHost().equalsIgnoreCase(b.getHost())&&("https".equalsIgnoreCase(u.getScheme())||isLocal(u.getHost()));}
    private void saveNavigationUrl(String url){if(url==null)return;Uri current=Uri.parse(url);if(internal(current)&&current.getPath()!=null&&current.getPath().startsWith("/routes"))getSharedPreferences("driver_navigation",MODE_PRIVATE).edit().putString("last_route_url",url).apply();}
    private void installNavigationObserver(){String js="(function(){if(window.__adimaxNavigationObserver)return;window.__adimaxNavigationObserver=true;function save(){try{AndroidNavigation.saveUrl(location.href)}catch(e){}};['pushState','replaceState'].forEach(function(k){var original=history[k];history[k]=function(){var result=original.apply(this,arguments);save();return result;};});addEventListener('popstate',save);addEventListener('hashchange',save);save();})();";webView.evaluateJavascript(js,null);}
    private void openExternal(String url){try{startActivity(new Intent(Intent.ACTION_VIEW,Uri.parse(url)));}catch(ActivityNotFoundException e){Toast.makeText(this,"Não foi possível abrir o arquivo.",Toast.LENGTH_SHORT).show();}}
    private void checkForUpdate(){new Thread(()->{HttpURLConnection c=null;try{c=(HttpURLConnection)new URL(BuildConfig.UPDATE_URL).openConnection();c.setConnectTimeout(10000);c.setReadTimeout(10000);c.setRequestProperty("Cache-Control","no-cache");try(InputStream in=c.getInputStream()){String json=new String(in.readAllBytes(),java.nio.charset.StandardCharsets.UTF_8);JSONObject o=new JSONObject(json);int code=o.getInt("versionCode");if(code>BuildConfig.VERSION_CODE){String apk=o.getString("apkUrl");String message=o.optString("message","Uma nova versão está disponível.");boolean required=o.optBoolean("required",false);runOnUiThread(()->showUpdateDialog(apk,message,required));}}}catch(Exception ignored){}finally{if(c!=null)c.disconnect();}}).start();}
    private void showUpdateDialog(String apkUrl,String message,boolean required){if(isFinishing()||isDestroyed())return;AlertDialog.Builder b=new AlertDialog.Builder(this).setTitle("Atualização disponível").setMessage(message).setPositiveButton("Atualizar",(d,w)->downloadUpdate(apkUrl));if(!required)b.setNegativeButton("Depois",null);b.setCancelable(!required).show();}
    private void downloadUpdate(String apkUrl){Toast.makeText(this,"Baixando atualização…",Toast.LENGTH_LONG).show();new Thread(()->{HttpURLConnection c=null;try{c=(HttpURLConnection)new URL(apkUrl).openConnection();c.setConnectTimeout(15000);c.setReadTimeout(60000);if(c.getResponseCode()!=HttpURLConnection.HTTP_OK)throw new IOException("HTTP "+c.getResponseCode());File apk=new File(getCacheDir(),"adimax-log-update.apk");try(InputStream in=c.getInputStream();FileOutputStream out=new FileOutputStream(apk)){byte[] buf=new byte[16384];int n;while((n=in.read(buf))>0)out.write(buf,0,n);}if(apk.length()<100000)throw new IOException("APK incompleto");runOnUiThread(()->{Toast.makeText(this,"Download concluído. Abrindo instalador…",Toast.LENGTH_SHORT).show();installUpdate(apk);});}catch(Exception e){runOnUiThread(()->Toast.makeText(this,"Não foi possível baixar a atualização.",Toast.LENGTH_LONG).show());}finally{if(c!=null)c.disconnect();}}).start();}
    private void installUpdate(File apk){if(android.os.Build.VERSION.SDK_INT>=26&&!getPackageManager().canRequestPackageInstalls()){pendingInstallApk=apk;Toast.makeText(this,"Ative 'Permitir desta fonte'. A instalação continuará ao voltar.",Toast.LENGTH_LONG).show();startActivity(new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,Uri.parse("package:"+getPackageName())));return;}Uri uri=FileProvider.getUriForFile(this,getPackageName()+".files",apk);Intent i=new Intent(Intent.ACTION_INSTALL_PACKAGE);i.setData(uri);i.setClipData(ClipData.newRawUri("Atualização Adimax",uri));i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION|Intent.FLAG_ACTIVITY_NEW_TASK);try{startActivity(i);}catch(ActivityNotFoundException e){Toast.makeText(this,"Instalador do Android indisponível.",Toast.LENGTH_LONG).show();}}
    private class DriverWebViewClient extends WebViewClient{@Override public boolean shouldOverrideUrlLoading(WebView v,WebResourceRequest r){if(internal(r.getUrl()))return false;openExternal(r.getUrl().toString());return true;}@Override public void onPageFinished(WebView v,String u){swipeRefresh.setRefreshing(false);saveNavigationUrl(u);installNavigationObserver();super.onPageFinished(v,u);}@Override public boolean onRenderProcessGone(WebView view,RenderProcessGoneDetail detail){saveNavigationUrl(view.getUrl());pauseLocationUpdates();runOnUiThread(()->{Toast.makeText(MainActivity.this,"Restaurando a tela aberta…",Toast.LENGTH_SHORT).show();recreate();});return true;}}
    private class DriverChromeClient extends WebChromeClient{
        @Override public void onGeolocationPermissionsShowPrompt(String origin,GeolocationPermissions.Callback cb){if(!internal(Uri.parse(origin))){cb.invoke(origin,false,false);return;}if(hasLocationPermission())cb.invoke(origin,true,false);else{pendingGeoOrigin=origin;pendingGeoCallback=cb;ActivityCompat.requestPermissions(MainActivity.this,new String[]{Manifest.permission.ACCESS_FINE_LOCATION,Manifest.permission.ACCESS_COARSE_LOCATION},LOCATION_PERMISSION);}}
        @Override public boolean onShowFileChooser(WebView v,ValueCallback<Uri[]> cb,FileChooserParams p){if(fileCallback!=null)fileCallback.onReceiveValue(null);fileCallback=cb;if(ContextCompat.checkSelfPermission(MainActivity.this,Manifest.permission.CAMERA)!=PackageManager.PERMISSION_GRANTED)ActivityCompat.requestPermissions(MainActivity.this,new String[]{Manifest.permission.CAMERA},CAMERA_PERMISSION);else launchFileChooser();return true;}
    }
    private void launchFileChooser(){
        cameraOutput=null;
        Intent docs=new Intent(Intent.ACTION_OPEN_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType("*/*");
        docs.putExtra(Intent.EXTRA_MIME_TYPES,new String[]{"image/*","application/pdf"});
        Intent camera=null;
        if(ContextCompat.checkSelfPermission(this,Manifest.permission.CAMERA)==PackageManager.PERMISSION_GRANTED){
            try{
                File dir=new File(getCacheDir(),"camera");
                if(!dir.exists()&&!dir.mkdirs())throw new IOException("Câmera indisponível");
                File photo=File.createTempFile("evidencia_"+new SimpleDateFormat("yyyyMMdd_HHmmss",Locale.US).format(new Date()),".jpg",dir);
                cameraOutput=FileProvider.getUriForFile(this,getPackageName()+".files",photo);
                camera=new Intent(MediaStore.ACTION_IMAGE_CAPTURE).putExtra(MediaStore.EXTRA_OUTPUT,cameraOutput);
                camera.setClipData(ClipData.newRawUri("Foto",cameraOutput));
                camera.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION|Intent.FLAG_GRANT_WRITE_URI_PERMISSION);
            }catch(IOException|IllegalArgumentException e){camera=null;cameraOutput=null;}
        }
        Intent chooser=Intent.createChooser(docs,"Enviar comprovante");
        if(camera!=null)chooser.putExtra(Intent.EXTRA_INITIAL_INTENTS,new Intent[]{camera});
        try{startActivityForResult(chooser,FILE_CHOOSER);}catch(ActivityNotFoundException|SecurityException e){
            if(fileCallback!=null)fileCallback.onReceiveValue(null);
            fileCallback=null;cameraOutput=null;
            Toast.makeText(this,"Não foi possível abrir a câmera ou os arquivos.",Toast.LENGTH_LONG).show();
        }
    }
    @Override protected void onActivityResult(int req,int result,Intent data){super.onActivityResult(req,result,data);if(req!=FILE_CHOOSER||fileCallback==null)return;Uri[] uris=null;if(result==Activity.RESULT_OK){if(data==null||data.getData()==null)uris=cameraOutput==null?null:new Uri[]{cameraOutput};else uris=WebChromeClient.FileChooserParams.parseResult(result,data);}fileCallback.onReceiveValue(uris);fileCallback=null;cameraOutput=null;}
    @Override public void onRequestPermissionsResult(int req,@NonNull String[] permissions,@NonNull int[] results){super.onRequestPermissionsResult(req,permissions,results);if(req==LOCATION_PERMISSION){boolean ok=hasLocationPermission();if(pendingGeoCallback!=null)pendingGeoCallback.invoke(pendingGeoOrigin,ok,false);pendingGeoCallback=null;pendingGeoOrigin=null;if(ok)startLocationUpdates(120000L);}else if(req==CAMERA_PERMISSION)launchFileChooser();}
    private boolean hasLocationPermission(){return ContextCompat.checkSelfPermission(this,Manifest.permission.ACCESS_FINE_LOCATION)==PackageManager.PERMISSION_GRANTED||ContextCompat.checkSelfPermission(this,Manifest.permission.ACCESS_COARSE_LOCATION)==PackageManager.PERMISSION_GRANTED;}
    @SuppressLint("MissingPermission") private void startLocationUpdates(long interval){locationRequested=true;locationInterval=Math.max(interval,15000L);if(!hasLocationPermission()){ActivityCompat.requestPermissions(this,new String[]{Manifest.permission.ACCESS_FINE_LOCATION,Manifest.permission.ACCESS_COARSE_LOCATION},LOCATION_PERMISSION);return;}ContextCompat.startForegroundService(this,new Intent(this,TrackingForegroundService.class));pauseLocationUpdates();locationListener=this::publishLocation;if(locationManager.isProviderEnabled(LocationManager.GPS_PROVIDER))locationManager.requestLocationUpdates(LocationManager.GPS_PROVIDER,locationInterval,10f,locationListener);if(locationManager.isProviderEnabled(LocationManager.NETWORK_PROVIDER))locationManager.requestLocationUpdates(LocationManager.NETWORK_PROVIDER,locationInterval,10f,locationListener);}
    private void pauseLocationUpdates(){if(locationListener!=null&&locationManager!=null)locationManager.removeUpdates(locationListener);locationListener=null;}
    private void stopLocationUpdates(){locationRequested=false;pauseLocationUpdates();stopService(new Intent(this,TrackingForegroundService.class));}
    private void publishLocation(Location l){String at=new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ssXXX",Locale.US).format(new Date(l.getTime()));String js=String.format(Locale.US,"window.onAndroidLocation&&window.onAndroidLocation(%f,%f,%f,%f,'%s')",l.getLatitude(),l.getLongitude(),l.getAccuracy(),l.hasSpeed()?l.getSpeed():0f,at);webView.post(()->webView.evaluateJavascript(js,null));}
    public class AndroidLocationBridge{
        @JavascriptInterface public void requestPermission(){runOnUiThread(()->{if(!hasLocationPermission())ActivityCompat.requestPermissions(MainActivity.this,new String[]{Manifest.permission.ACCESS_FINE_LOCATION,Manifest.permission.ACCESS_COARSE_LOCATION},LOCATION_PERMISSION);});}
        @JavascriptInterface public void requestAllPermissions(){runOnUiThread(()->{if(android.os.Build.VERSION.SDK_INT>=33)ActivityCompat.requestPermissions(MainActivity.this,new String[]{Manifest.permission.ACCESS_FINE_LOCATION,Manifest.permission.ACCESS_COARSE_LOCATION,Manifest.permission.CAMERA,Manifest.permission.POST_NOTIFICATIONS},INITIAL_PERMISSIONS);else ActivityCompat.requestPermissions(MainActivity.this,new String[]{Manifest.permission.ACCESS_FINE_LOCATION,Manifest.permission.ACCESS_COARSE_LOCATION,Manifest.permission.CAMERA},INITIAL_PERMISSIONS);});}
        @JavascriptInterface public void showNotification(String title,String message,int notificationId){runOnUiThread(()->showOperationalNotification(title,message,notificationId));}
        @JavascriptInterface public void startLocationUpdates(int intervalMs){runOnUiThread(()->MainActivity.this.startLocationUpdates(Math.max(intervalMs,15000)));}
        @JavascriptInterface public void stopLocationUpdates(){runOnUiThread(MainActivity.this::stopLocationUpdates);}
    }
    public class AndroidNavigationBridge{
        @JavascriptInterface public void saveUrl(String url){saveNavigationUrl(url);}
    }
}
