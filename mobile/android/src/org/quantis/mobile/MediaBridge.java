package org.quantis.mobile;

import android.app.Activity;
import android.app.Application;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.drawable.Icon;
import android.media.MediaMetadata;
import android.media.session.MediaSession;
import android.media.session.PlaybackState;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.view.View;
import android.view.Window;
import android.view.WindowInsetsController;

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
    public static final long LIKE = 5;
    public static final long REPEAT = 6;
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
    private static String source = ""; // подпись: «Яндекс Музыка», «Моя волна»…
    private static boolean liked;
    private static int repeatMode; // 0 — выкл, 1 — всё, 2 — один трек
    private static String coverPath = "";
    private static Bitmap cover;

    private static final String ACTION_LIKE = "org.quantis.mobile.LIKE";
    private static final String ACTION_REPEAT = "org.quantis.mobile.REPEAT";

    private MediaBridge() {
    }

    public static void init(final Context ctx) {
        main.post(() -> setup(ctx.getApplicationContext()));
        main.post(() -> styleSystemBars(20));
    }

    /** Фон приложения (Theme.bg) для системных панелей. */
    private static final int BAR_COLOR = 0xFF0B0D12;

    /**
     * Панель навигации и строка состояния — в цвет приложения, значки светлые.
     * Тема p4a оставляла панель навигации белой. Окно активности может ещё
     * не появиться: тогда пробуем снова через 250 мс (attempts раз).
     */
    private static void styleSystemBars(final int attempts) {
        Activity activity = null;
        try {
            activity = (Activity) Class.forName("org.kivy.android.PythonActivity")
                    .getField("mActivity").get(null);
        } catch (ReflectiveOperationException | ClassCastException e) {
            Log.w(TAG, "no activity for system bars", e);
        }
        if (activity == null || activity.getWindow() == null) {
            if (attempts > 0) {
                main.postDelayed(() -> styleSystemBars(attempts - 1), 250);
            }
            return;
        }
        Window window = activity.getWindow();
        window.setNavigationBarColor(BAR_COLOR);
        window.setStatusBarColor(BAR_COLOR);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            window.setNavigationBarContrastEnforced(false);
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            WindowInsetsController controller = window.getInsetsController();
            if (controller != null) {
                controller.setSystemBarsAppearance(0,
                        WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS
                                | WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS);
            }
        } else {
            View decor = window.getDecorView();
            decor.setSystemUiVisibility(decor.getSystemUiVisibility()
                    & ~View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR
                    & ~View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR);
        }
    }

    public static void update(final String newTitle, final String newArtist,
                              final boolean isPlaying, final long positionMs,
                              final long durationMs, final String newCoverPath,
                              final String newSource, final boolean isLiked,
                              final int newRepeatMode) {
        // Обложку декодируем здесь, в потоке Qt, а не в главном потоке Android.
        final String path = newCoverPath == null ? "" : newCoverPath;
        final Bitmap decoded = path.equals(coverPath) ? null : decodeCover(path);
        main.post(() -> {
            title = newTitle == null ? "" : newTitle;
            artist = newArtist == null ? "" : newArtist;
            playing = isPlaying;
            position = Math.max(0, positionMs);
            duration = Math.max(0, durationMs);
            source = newSource == null ? "" : newSource;
            liked = isLiked;
            repeatMode = newRepeatMode;
            if (!path.equals(coverPath)) {
                coverPath = path;
                cover = decoded;
            }
            publish();
        });
    }

    /** Обложка из кэша Python на диске, до ~512 px; null — нет или не читается. */
    private static Bitmap decodeCover(String path) {
        if (path.isEmpty()) {
            return null;
        }
        try {
            BitmapFactory.Options bounds = new BitmapFactory.Options();
            bounds.inJustDecodeBounds = true;
            BitmapFactory.decodeFile(path, bounds);
            int sample = 1;
            while (Math.max(bounds.outWidth, bounds.outHeight) / (sample * 2) >= 512) {
                sample *= 2;
            }
            BitmapFactory.Options options = new BitmapFactory.Options();
            options.inSampleSize = sample;
            return BitmapFactory.decodeFile(path, options);
        } catch (RuntimeException e) {
            Log.w(TAG, "Обложка не прочиталась: " + path, e);
            return null;
        }
    }

    /** Значок из res/ библиотеки (своего R нет) или запасной системный. */
    private static int drawable(Context ctx, String name, int fallback) {
        int id = ctx.getResources().getIdentifier(name, "drawable", ctx.getPackageName());
        return id != 0 ? id : fallback;
    }

    private static String repeatIcon() {
        return repeatMode == 2 ? "quantis_repeat_one"
                : repeatMode == 1 ? "quantis_repeat" : "quantis_repeat_off";
    }

    private static String repeatLabel() {
        return repeatMode == 2 ? "Повтор трека" : repeatMode == 1 ? "Повтор всего" : "Без повтора";
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

    /** Окно Python уже поднято в этом процессе (служба не сирота). */
    static boolean ready() {
        return context != null;
    }

    /**
     * Закрытие окна Qt на Android взаимно блокируется: главный поток в
     * QtActivityBase.onDestroy ждёт поток Qt, тот — поток отрисовки, а
     * отрисовка (eglSwapBuffers) — главный поток. Через 20 с система пишет
     * «не отвечает» и убивает процесс. Поэтому завершаем процесс сами до
     * onDestroy: состояние (лайки, история, плейлисты) Python сохраняет сразу
     * при изменении, а без окна Qt плеер всё равно не живёт.
     */
    private static void watchActivityDestroy(Context ctx) {
        if (!(ctx instanceof Application)) {
            return;
        }
        ((Application) ctx).registerActivityLifecycleCallbacks(
                new Application.ActivityLifecycleCallbacks() {
                    @Override
                    public void onActivityPreDestroyed(Activity activity) {
                        if (activity.isChangingConfigurations()) {
                            return;
                        }
                        Log.i(TAG, "Окно закрывается — завершаем процесс");
                        NotificationManager nm = ctx.getSystemService(NotificationManager.class);
                        if (nm != null) {
                            nm.cancel(NOTIFICATION_ID);
                        }
                        // Служба остановлена явно — система не станет
                        // перезапускать её как «упавшую».
                        ctx.stopService(new Intent(ctx, PlaybackService.class));
                        android.os.Process.killProcess(android.os.Process.myPid());
                    }

                    @Override
                    public void onActivityCreated(Activity a, Bundle b) {
                    }

                    @Override
                    public void onActivityStarted(Activity a) {
                    }

                    @Override
                    public void onActivityResumed(Activity a) {
                    }

                    @Override
                    public void onActivityPaused(Activity a) {
                    }

                    @Override
                    public void onActivityStopped(Activity a) {
                    }

                    @Override
                    public void onActivitySaveInstanceState(Activity a, Bundle b) {
                    }

                    @Override
                    public void onActivityDestroyed(Activity a) {
                    }
                });
    }

    private static void setup(Context ctx) {
        if (session != null) {
            return;
        }
        context = ctx;
        watchActivityDestroy(ctx);
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

            @Override
            public void onCustomAction(String action, android.os.Bundle extras) {
                if (ACTION_LIKE.equals(action)) {
                    commands.add(LIKE);
                } else if (ACTION_REPEAT.equals(action)) {
                    commands.add(REPEAT);
                }
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
        // Обложка — фон плеера в шторке (Android 13+) и картинка уведомления.
        MediaMetadata.Builder metadata = new MediaMetadata.Builder()
                .putString(MediaMetadata.METADATA_KEY_TITLE, title)
                // Плеер в шторке (Android 13+) показывает только название и
                // исполнителя — подпись уведомления и альбом он не выводит.
                // Источник — во второй строке, после исполнителя.
                .putString(MediaMetadata.METADATA_KEY_ARTIST,
                        source.isEmpty() ? artist
                                : artist.isEmpty() ? source : artist + " · " + source)
                .putString(MediaMetadata.METADATA_KEY_ALBUM, source)
                .putLong(MediaMetadata.METADATA_KEY_DURATION, duration);
        if (cover != null) {
            metadata.putBitmap(MediaMetadata.METADATA_KEY_ALBUM_ART, cover);
            metadata.putBitmap(MediaMetadata.METADATA_KEY_ART, cover);
        }
        session.setMetadata(metadata.build());
        // «Нравится» и повтор — свои кнопки рядом с перемоткой (Android 13+
        // берёт их из состояния сессии, а не из кнопок уведомления).
        session.setPlaybackState(new PlaybackState.Builder()
                .setActions(PlaybackState.ACTION_PLAY | PlaybackState.ACTION_PAUSE
                        | PlaybackState.ACTION_PLAY_PAUSE
                        | PlaybackState.ACTION_SKIP_TO_NEXT
                        | PlaybackState.ACTION_SKIP_TO_PREVIOUS
                        | PlaybackState.ACTION_SEEK_TO)
                .setState(playing ? PlaybackState.STATE_PLAYING : PlaybackState.STATE_PAUSED,
                        position, playing ? 1f : 0f)
                .addCustomAction(new PlaybackState.CustomAction.Builder(
                        ACTION_LIKE, liked ? "Убрать из «Нравится»" : "Нравится",
                        drawable(context, liked ? "quantis_liked" : "quantis_like",
                                android.R.drawable.star_off)).build())
                .addCustomAction(new PlaybackState.CustomAction.Builder(
                        ACTION_REPEAT, repeatLabel(),
                        drawable(context, repeatIcon(), android.R.drawable.ic_menu_rotate)).build())
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
        // Кнопки — для Android до 13 (новые берут их из сессии): сердце,
        // назад, пауза, дальше, повтор; в свёрнутом виде — средние три.
        Notification.Builder builder = new Notification.Builder(ctx, CHANNEL)
                .setSmallIcon(drawable(ctx, "quantis_stat", android.R.drawable.ic_media_play))
                .setColor(0xFFFF2A7F)
                .setContentTitle(title)
                .setContentText(artist)
                .setSubText(source)
                .setOnlyAlertOnce(true)
                .setShowWhen(false)
                .setVisibility(Notification.VISIBILITY_PUBLIC)
                .addAction(action(ctx, drawable(ctx, liked ? "quantis_liked" : "quantis_like",
                        android.R.drawable.star_off), liked ? "Убрать из «Нравится»" : "Нравится", LIKE))
                .addAction(action(ctx, android.R.drawable.ic_media_previous, "Назад", PREV))
                .addAction(playing
                        ? action(ctx, android.R.drawable.ic_media_pause, "Пауза", PAUSE)
                        : action(ctx, android.R.drawable.ic_media_play, "Играть", PLAY))
                .addAction(action(ctx, android.R.drawable.ic_media_next, "Дальше", NEXT))
                .addAction(action(ctx, drawable(ctx, repeatIcon(), android.R.drawable.ic_menu_rotate),
                        repeatLabel(), REPEAT));
        if (cover != null) {
            builder.setLargeIcon(cover);
        }
        if (session != null) {
            builder.setStyle(new Notification.MediaStyle()
                    .setMediaSession(session.getSessionToken())
                    .setShowActionsInCompactView(1, 2, 3));
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
