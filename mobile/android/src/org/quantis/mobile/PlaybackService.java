package org.quantis.mobile;

import android.app.Service;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.os.IBinder;

/**
 * Служба переднего плана на время воспроизведения. В том же процессе, что и
 * приложение: пока она работает, Android не замораживает свёрнутый Quantis,
 * и цикл Qt переключает треки.
 */
public class PlaybackService extends Service {
    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        startForeground(MediaBridge.NOTIFICATION_ID, MediaBridge.buildNotification(this),
                ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK);
        return START_NOT_STICKY;
    }

    @Override
    public void onTaskRemoved(Intent rootIntent) {
        // Приложение смахнули из недавних: плеер вместе с ним закрывается.
        stopForeground(STOP_FOREGROUND_REMOVE);
        stopSelf();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
