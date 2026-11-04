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
        if (!MediaBridge.ready()) {
            // Android сам перезапустил службу после гибели процесса — без
            // окна и Python. Такой процесс-сирота не отвечал, когда в него
            // потом открывали приложение: останавливаемся.
            stopSelf();
            return START_NOT_STICKY;
        }
        startForeground(MediaBridge.NOTIFICATION_ID, MediaBridge.buildNotification(this),
                ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK);
        return START_NOT_STICKY;
    }

    @Override
    public void onDestroy() {
        super.onDestroy();
        if (!MediaBridge.ready()) {
            // Сирота остановлен — убираем и процесс, чтобы приложение
            // открылось с чистого запуска.
            android.os.Process.killProcess(android.os.Process.myPid());
        }
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
