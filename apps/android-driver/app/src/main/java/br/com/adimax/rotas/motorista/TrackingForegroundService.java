package br.com.adimax.rotas.motorista;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.os.IBinder;
import androidx.annotation.Nullable;
import androidx.core.app.NotificationCompat;

/** Keeps the authorized driver session alive while a route is eligible for tracking. */
public class TrackingForegroundService extends Service {
    private static final String CHANNEL = "adimax_route_tracking";
    @Override public void onCreate() {
        super.onCreate();
        NotificationManager manager = getSystemService(NotificationManager.class);
        manager.createNotificationChannel(new NotificationChannel(CHANNEL, "Rastreamento de rota", NotificationManager.IMPORTANCE_LOW));
    }
    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        Intent open = new Intent(this, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP);
        PendingIntent pending = PendingIntent.getActivity(this, 0, open, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        Notification notification = new NotificationCompat.Builder(this, CHANNEL)
            .setSmallIcon(R.mipmap.ic_launcher).setContentTitle("Adimax Motorista")
            .setContentText("Rastreamento ativo durante sua rota")
            .setOngoing(true).setContentIntent(pending).setCategory(NotificationCompat.CATEGORY_SERVICE).build();
        startForeground(1201, notification);
        return START_STICKY;
    }
    @Nullable @Override public IBinder onBind(Intent intent) { return null; }
}
