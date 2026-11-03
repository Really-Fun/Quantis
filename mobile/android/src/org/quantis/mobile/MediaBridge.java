package org.quantis.mobile;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.graphics.drawable.Icon;
import android.media.MediaMetadata;
import android.media.session.MediaSession;
import android.media.session.PlaybackState;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;

import java.util.concurrent.ConcurrentLinkedQueue;

/**
 * Плашка плеера в шторке и на экране блокировки: MediaSession + уведомление
 * MediaStyle. Python вызывает статические методы через JNI из потока Qt, а
 * нажатия кнопок забирает опросом poll(): обратных вызовов в Python нет.
 * Вся работа с сессией и уведомлением идёт в главном потоке Android.
 */
public final class MediaBridge {
    public static final long NONE = -1;
    public static final long PLAY = 1;
    public static final long PAUSE = 2;
    public static final long NEXT = 3;
    public static final long PREV = 4;
    /** Перемотка: SEEK_BASE + позиция в мс. */
    public static final long SEEK_BASE = 10;

    static final int NOTIFICATION_ID = 7301;
    private static final String TAG = "QuantisMedia";
    private static final String CHANNEL = "quantis_playback";
    private static final String ACTION = "org.quantis.mobile.MEDIA_COMMAND";
    private static final String EXTRA = "command";

    private static final ConcurrentLinkedQueue<Long> commands = new ConcurrentLinkedQueue<>();
    private static final Handler main = new Handler(Looper.getMainLooper());

    private static Context context;
    private static MediaSession session;
    private static String title = "";
    private static String artist = "";
    private static boolean playing;
    private static long position;
    private static long duration;
    private static boolean serviceStarted;

    private MediaBridge() {
    }

    public static void init(final Context ctx) {
        main.post(() -> setup(ctx.getApplicationContext()));
    }

    public static void update(final String newTitle, final String newArtist,
                              final boolean isPlaying, final long positionMs,
                              final long durationMs) {
        main.post(() -> {
            title = newTitle == null ? "" : newTitle;
            artist = newArtist == null ? "" : newArtist;
            playing = isPlaying;
            position = Math.max(0, positionMs);
            duration = Math.max(0, durationMs);
            publish();
        });
    }

    /** Системные анимации включены (в «Для разработчиков» их можно выключить). */
    public static boolean animatorsEnabled() {
        return android.animation.ValueAnimator.areAnimatorsEnabled();
    }

    /** Следующая команда кнопок или NONE. */
    public static long poll() {
        Long command = commands.poll();
        return command == null ? NONE : command;
    }

    public static void release() {
        main.post(() -> {
            if (context != null) {
                context.stopService(new Intent(context, PlaybackService.class));
                NotificationManager nm = context.getSystemService(NotificationManager.class);
                if (nm != null) {
                    nm.cancel(NOTIFICATION_ID);
                }
            }
            serviceStarted = false;
            if (session != null) {
                session.setActive(false);
                session.release();
                session = null;
            }
        });
    }

    private static void setup(Context ctx) {
        if (session != null) {
            return;
        }
        context = ctx;
        NotificationManager nm = ctx.getSystemService(NotificationManager.class);
        if (nm != null) {
            NotificationChannel channel = new NotificationChannel(
                    CHANNEL, "Воспроизведение", NotificationManager.IMPORTANCE_LOW);
            channel.setShowBadge(false);
            nm.createNotificationChannel(channel);
        }
        session = new MediaSession(ctx, "Quantis");
        session.setCallback(new MediaSession.Callback() {
            @Override
            public void onPlay() {
                commands.add(PLAY);
            }

            @Override
            public void onPause() {
                commands.add(PAUSE);
            }

            @Override
            public void onSkipToNext() {
                commands.add(NEXT);
            }

            @Override
            public void onSkipToPrevious() {
                commands.add(PREV);
            }

            @Override
            public void onSeekTo(long pos) {
                commands.add(SEEK_BASE + Math.max(0, pos));
            }
        }, main);
        session.setActive(true);

        BroadcastReceiver receiver = new BroadcastReceiver() {
            @Override
            public void onReceive(Context c, Intent intent) {
                long command = intent.getLongExtra(EXTRA, NONE);
                if (command != NONE) {
                    commands.add(command);
                }
            }
        };
        IntentFilter filter = new IntentFilter(ACTION);
        if (Build.VERSION.SDK_INT >= 33) {
            ctx.registerReceiver(receiver, filter, Context.RECEIVER_NOT_EXPORTED);
        } else {
            ctx.registerReceiver(receiver, filter);
        }
    }

    private static void publish() {
        if (session == null || context == null) {
            return;
        }
        session.setMetadata(new MediaMetadata.Builder()
                .putString(MediaMetadata.METADATA_KEY_TITLE, title)
                .putString(MediaMetadata.METADATA_KEY_ARTIST, artist)
                .putLong(MediaMetadata.METADATA_KEY_DURATION, duration)
                .build());
        session.setPlaybackState(new PlaybackState.Builder()
                .setActions(PlaybackState.ACTION_PLAY | PlaybackState.ACTION_PAUSE
                        | PlaybackState.ACTION_PLAY_PAUSE
                        | PlaybackState.ACTION_SKIP_TO_NEXT
                        | PlaybackState.ACTION_SKIP_TO_PREVIOUS
                        | PlaybackState.ACTION_SEEK_TO)
                .setState(playing ? PlaybackState.STATE_PLAYING : PlaybackState.STATE_PAUSED,
                        position, playing ? 1f : 0f)
                .build());

        if (!serviceStarted && playing) {
            // Служба переднего плана: без неё Android замораживает свёрнутое
            // приложение, и следующий трек не включается.
            try {
                context.startForegroundService(new Intent(context, PlaybackService.class));
                serviceStarted = true;
                return; // уведомление покажет сама служба
            } catch (RuntimeException e) {
                Log.w(TAG, "Служба переднего плана не запущена", e);
            }
        }
        NotificationManager nm = context.getSystemService(NotificationManager.class);
        if (nm != null) {
            nm.notify(NOTIFICATION_ID, buildNotification(context));
        }
    }

    static Notification buildNotification(Context ctx) {
        Notification.Builder builder = new Notification.Builder(ctx, CHANNEL)
                .setSmallIcon(android.R.drawable.ic_media_play)
                .setContentTitle(title)
                .setContentText(artist)
                .setOnlyAlertOnce(true)
                .setShowWhen(false)
                .setVisibility(Notification.VISIBILITY_PUBLIC)
                .addAction(action(ctx, android.R.drawable.ic_media_previous, "Назад", PREV))
                .addAction(playing
                        ? action(ctx, android.R.drawable.ic_media_pause, "Пауза", PAUSE)
                        : action(ctx, android.R.drawable.ic_media_play, "Играть", PLAY))
                .addAction(action(ctx, android.R.drawable.ic_media_next, "Дальше", NEXT));
        if (session != null) {
            builder.setStyle(new Notification.MediaStyle()
                    .setMediaSession(session.getSessionToken())
                    .setShowActionsInCompactView(0, 1, 2));
        }
        Intent launch = ctx.getPackageManager().getLaunchIntentForPackage(ctx.getPackageName());
        if (launch != null) {
            builder.setContentIntent(PendingIntent.getActivity(
                    ctx, 0, launch, PendingIntent.FLAG_IMMUTABLE));
        }
        return builder.build();
    }

    private static Notification.Action action(Context ctx, int icon, String label, long command) {
        Intent intent = new Intent(ACTION).setPackage(ctx.getPackageName()).putExtra(EXTRA, command);
        PendingIntent pending = PendingIntent.getBroadcast(ctx, (int) command, intent,
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        return new Notification.Action.Builder(
                Icon.createWithResource(ctx, icon), label, pending).build();
    }
}
