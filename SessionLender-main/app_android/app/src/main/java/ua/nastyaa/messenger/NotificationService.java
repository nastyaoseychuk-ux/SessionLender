package ua.nastyaa.messenger;

import android.app.*;
import android.content.*;
import android.content.pm.ServiceInfo;
import android.os.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;
import java.util.concurrent.TimeUnit;
import okhttp3.*;
import org.json.*;

/** A visible foreground service for test WebSocket notifications. Not an FCM replacement. */
public class NotificationService extends Service {

  private static final String STATUS = "connection";
  private static final String EVENTS = "events_water_droplet_75_v2";
  private final Handler handler = new Handler(Looper.getMainLooper());
  private final OkHttpClient client = new OkHttpClient.Builder()
    .pingInterval(30, TimeUnit.SECONDS)
    .readTimeout(0, TimeUnit.SECONDS)
    .build();
  private WebSocket socket;
  private String cookie = "",
    accountKey = "";
  private int generation = 0,
    delay = 1000;
  private boolean stopped;
  private NotificationManager manager;
  private final LinkedHashSet<String> seen = new LinkedHashSet<>();

  @Override
  public void onCreate() {
    super.onCreate();
    manager = getSystemService(NotificationManager.class);
    manager.createNotificationChannel(
      new NotificationChannel(
        STATUS,
        "З’єднання із сервером",
        NotificationManager.IMPORTANCE_LOW
      )
    );
    NotificationChannel events = new NotificationChannel(
      EVENTS, "Повідомлення та події", NotificationManager.IMPORTANCE_HIGH);
    events.setSound(
      android.net.Uri.parse("android.resource://" + getPackageName() + "/raw/notification"),
      new android.media.AudioAttributes.Builder()
        .setUsage(android.media.AudioAttributes.USAGE_NOTIFICATION)
        .setContentType(android.media.AudioAttributes.CONTENT_TYPE_SONIFICATION)
        .build());
    manager.createNotificationChannel(events);
    Notification notification = statusNotification(
      "Сповіщення сервера активні"
    );
    if (Build.VERSION.SDK_INT >= 34) startForeground(
      1,
      notification,
      ServiceInfo.FOREGROUND_SERVICE_TYPE_REMOTE_MESSAGING
    );
    else startForeground(1, notification);
  }

  @Override
  public int onStartCommand(Intent intent, int flags, int startId) {
    if (intent == null || intent.getStringExtra("cookie") == null) {
      stopSelf();
      return START_NOT_STICKY;
    }
    String value = intent.getStringExtra("cookie");
    if (!value.equals(cookie)) {
      changeSession(value);
    }
    return START_NOT_STICKY;
  }

  private void changeSession(String value) {
    generation++;
    handler.removeCallbacksAndMessages(null);
    if (socket != null) socket.cancel();
    for (String old : seen) manager.cancel(2 + (old.hashCode() & 0x3fffffff));
    cookie = value;
    accountKey = fingerprint(value);
    seen.clear();
    loadSeenEvents();
    stopped = false;
    delay = 1000;
    connect();
  }

  private void loadSeenEvents() {
    String stored = getSharedPreferences(
      "notifications",
      MODE_PRIVATE
    ).getString(accountKey, "[]");
    try {
      JSONArray data = new JSONArray(stored);
      for (int i = 0; i < data.length(); i++) seen.add(data.getString(i));
    } catch (JSONException ignored) {}
  }

  private static String fingerprint(String value) {
    try {
      byte[] hash = MessageDigest.getInstance("SHA-256").digest(
        value.getBytes(StandardCharsets.UTF_8)
      );
      StringBuilder out = new StringBuilder();
      for (byte b : hash)
        out.append(String.format(Locale.ROOT, "%02x", b & 255));
      return out.toString();
    } catch (Exception error) {
      throw new IllegalStateException(error);
    }
  }

  private void connect() {
    if (stopped) return;
    final int current = ++generation;
    String url = ServerConfig.BASE_URL + "/ws/inbox/";
    Request request = new Request.Builder()
      .url(url)
      .header("Cookie", cookie)
      .header("Origin", ServerConfig.BASE_URL)
      .build();
    socket = client.newWebSocket(request, connectionListener(current));
  }

  private WebSocketListener connectionListener(int current) {
    return new WebSocketListener() {
      @Override
      public void onOpen(WebSocket ws, Response response) {
        handler.post(() -> {
          if (current == generation) {
            delay = 1000;
            updateStatus("Підключено до сервера");
          }
        });
      }

      @Override
      public void onMessage(WebSocket ws, String text) {
        handler.post(() -> {
          if (current == generation) receive(text);
        });
      }

      @Override
      public void onClosing(WebSocket ws, int code, String reason) {
        ws.close(code, reason);
      }

      @Override
      public void onClosed(WebSocket ws, int code, String reason) {
        handler.post(() -> {
          if (current != generation) return;
          if (code == 4403 || code == 1008) stopSelf();
          else reconnect(current);
        });
      }

      @Override
      public void onFailure(WebSocket ws, Throwable error, Response response) {
        handler.post(() -> {
          if (current != generation) return;
          if (
            response != null &&
            (response.code() == 401 || response.code() == 403)
          ) stopSelf();
          else reconnect(current);
        });
      }
    };
  }

  private void reconnect(int current) {
    if (stopped || current != generation) return;
    updateStatus("Відновлення з’єднання із сервером…");
    int wait = delay;
    delay = Math.min(delay * 2, 30000);
    handler.postDelayed(
      () -> {
        if (current == generation && !stopped) connect();
      },
      wait + new Random().nextInt(500)
    );
  }

  private void receive(String raw) {
    try {
      JSONObject event = new JSONObject(raw);
      if (!"notification".equals(event.optString("type"))) return;
      String id = event.getString("id");
      if (!seen.add(id)) return;
      while (seen.size() > 200) seen.remove(seen.iterator().next());
      getSharedPreferences("notifications", MODE_PRIVATE)
        .edit()
        .putString(accountKey, new JSONArray(seen).toString())
        .apply();
      showEvent(event, id);
    } catch (JSONException | SecurityException ignored) {}
  }

  private void showEvent(JSONObject event, String id) {
    int number = 2 + (id.hashCode() & 0x3fffffff);
    String body = event.optString("body", "Нова подія на сервері");
    Notification notification = new Notification.Builder(this, EVENTS)
      .setSmallIcon(R.drawable.ic_notification)
      .setContentTitle(event.optString("title", "SessionLender"))
      .setContentText(body)
      .setStyle(new Notification.BigTextStyle().bigText(body))
      .setAutoCancel(true)
      .setVisibility(Notification.VISIBILITY_PRIVATE)
      .setGroup("server_events")
      .setCategory(Notification.CATEGORY_MESSAGE)
      .setContentIntent(open(event.optString("path", "/messages/"), number))
      .build();
    manager.notify(number, notification);
  }

  private Notification statusNotification(String text) {
    return new Notification.Builder(this, STATUS)
      .setSmallIcon(R.drawable.ic_notification)
      .setContentTitle("SessionLender")
      .setContentText(text)
      .setOngoing(true)
      .setContentIntent(open("/", 0))
      .build();
  }

  private void updateStatus(String text) {
    manager.notify(1, statusNotification(text));
  }

  private PendingIntent open(String path, int number) {
    Intent intent = new Intent(this, MainActivity.class)
      .putExtra("path", path)
      .addFlags(
        Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP
      );
    return PendingIntent.getActivity(
      this,
      number,
      intent,
      PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
    );
  }

  @Override
  public void onDestroy() {
    stopped = true;
    generation++;
    handler.removeCallbacksAndMessages(null);
    if (socket != null) socket.cancel();
    client.dispatcher().executorService().shutdown();
    client.connectionPool().evictAll();
    cookie = "";
    for (String old : seen) manager.cancel(2 + (old.hashCode() & 0x3fffffff));
    stopForeground(STOP_FOREGROUND_REMOVE);
    super.onDestroy();
  }

  @Override
  public IBinder onBind(Intent intent) {
    return null;
  }
}
