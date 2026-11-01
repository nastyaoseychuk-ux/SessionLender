package ua.nastyaa.messenger;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.view.View;
import android.view.WindowInsets;
import android.webkit.CookieManager;
import android.webkit.PermissionRequest;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.LinearLayout;
import android.widget.Toast;

/** Java Android client. Website screens and authenticated WebSockets run in WebView. */
public class MainActivity extends Activity {

  private WebView web;
  private final String base = ServerConfig.BASE_URL;
  private ValueCallback<Uri[]> files;
  private static final int PICK_FILE = 42;
  private static final int MICROPHONE = 78;
  private PermissionRequest microphoneRequest;

  @Override
  public void onCreate(Bundle state) {
    super.onCreate(state);
    createLayout();
    configureWebView();
    configureNavigation();
    configureFileChooser();
    requestNotificationPermission();
    if (state == null || web.restoreState(state) == null) {
      String previous = state == null ? null : state.getString("lastUrl");
      if (previous != null && sameServer(Uri.parse(previous))) web.loadUrl(previous);
      else openNotification(getIntent());
    }
  }

  private void createLayout() {
    LinearLayout layout = new LinearLayout(this);
    layout.setOrientation(LinearLayout.VERTICAL);
    layout.setBackgroundColor(Color.rgb(16, 20, 28));
    web = new WebView(this);
    layout.addView(web, new LinearLayout.LayoutParams(-1, 0, 1));
    setContentView(layout);
    if (android.os.Build.VERSION.SDK_INT >= 30) {
      layout.setOnApplyWindowInsetsListener((v, insets) -> {
        android.graphics.Insets edges = insets.getInsets(
          WindowInsets.Type.systemBars()
        );
        v.setPadding(edges.left, edges.top, edges.right, edges.bottom);
        return insets;
      });
    }
    web.setBackgroundColor(Color.rgb(16, 20, 28));
  }

  private void configureWebView() {
    String userAgent = web.getSettings().getUserAgentString();
    web
      .getSettings()
      .setUserAgentString(
        userAgent + " SessionLenderAndroid/" + BuildConfig.VERSION_NAME
      );
    web.getSettings().setJavaScriptEnabled(true);
    web.getSettings().setDomStorageEnabled(true);
    web.getSettings().setAllowFileAccess(false);
    web.getSettings().setAllowContentAccess(true);
    web
      .getSettings()
      .setMixedContentMode(
        android.webkit.WebSettings.MIXED_CONTENT_NEVER_ALLOW
      );
    CookieManager.getInstance().setAcceptCookie(true);
    CookieManager.getInstance().setAcceptThirdPartyCookies(web, false);
  }

  private void configureNavigation() {
    web.setWebViewClient(
      new WebViewClient() {
        @Override
        public boolean shouldOverrideUrlLoading(
          WebView view,
          WebResourceRequest request
        ) {
          Uri uri = request.getUrl();
          if (sameServer(uri)) return false;
          if (
            "https".equals(uri.getScheme()) || "http".equals(uri.getScheme())
          ) {
            try {
              startActivity(new Intent(Intent.ACTION_VIEW, uri));
            } catch (Exception e) {
              Toast.makeText(
                MainActivity.this,
                "Немає браузера",
                Toast.LENGTH_SHORT
              ).show();
            }
          }
          return true;
        }

        @Override
        public void onPageStarted(WebView view, String url, android.graphics.Bitmap favicon) {
          cancelMicrophoneRequest();
        }

        @Override
        public void onPageFinished(WebView view, String url) {
          CookieManager.getInstance().flush();
          if (sameServer(Uri.parse(url))) syncNotifications();
        }

        @Override
        public void onReceivedError(
          WebView view,
          WebResourceRequest request,
          WebResourceError error
        ) {
          if (request.isForMainFrame()) Toast.makeText(
            MainActivity.this,
            "Сервер недоступний. Перевірте підключення до інтернету та відкрийте додаток повторно.",
            Toast.LENGTH_LONG
          ).show();
        }
      }
    );
  }

  private void configureFileChooser() {
    web.setWebChromeClient(
      new WebChromeClient() {
        @Override
        public void onPermissionRequest(PermissionRequest request) {
          runOnUiThread(() -> {
            if (!sameServer(request.getOrigin()) ||
                !sameServer(Uri.parse(web.getUrl() == null ? "" : web.getUrl())) ||
                !java.util.Arrays.asList(request.getResources()).contains(
                  PermissionRequest.RESOURCE_AUDIO_CAPTURE)) {
              request.deny();
              return;
            }
            if (microphoneRequest != null) {
              request.deny();
              return;
            }
            if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) ==
                PackageManager.PERMISSION_GRANTED) {
              request.grant(new String[] { PermissionRequest.RESOURCE_AUDIO_CAPTURE });
            } else {
              microphoneRequest = request;
              requestPermissions(new String[] { Manifest.permission.RECORD_AUDIO }, MICROPHONE);
            }
          });
        }

        @Override
        public void onPermissionRequestCanceled(PermissionRequest request) {
          runOnUiThread(() -> {
            if (microphoneRequest == request) microphoneRequest = null;
          });
        }

        @Override
        public boolean onShowFileChooser(
          WebView view,
          ValueCallback<Uri[]> callback,
          FileChooserParams params
        ) {
          if (files != null) files.onReceiveValue(null);
          files = callback;
          try {
            startActivityForResult(params.createIntent(), PICK_FILE);
            return true;
          } catch (Exception e) {
            files = null;
            return false;
          }
        }
      }
    );
  }

  private void cancelMicrophoneRequest() {
    if (microphoneRequest != null) {
      microphoneRequest.deny();
      microphoneRequest = null;
    }
  }

  private void requestNotificationPermission() {
    // No native JavaScript bridge and no TLS validation bypass.
    if (
      android.os.Build.VERSION.SDK_INT >= 33 &&
      checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) !=
        PackageManager.PERMISSION_GRANTED
    ) {
      requestPermissions(
        new String[] { Manifest.permission.POST_NOTIFICATIONS },
        77
      );
    }
  }

  private boolean sameServer(Uri uri) {
    Uri expected = Uri.parse(base);
    return (
      expected.getScheme().equals(uri.getScheme()) &&
      expected
        .getHost()
        .equalsIgnoreCase(uri.getHost() == null ? "" : uri.getHost()) &&
      effectivePort(expected) == effectivePort(uri)
    );
  }

  private static int effectivePort(Uri uri) {
    return uri.getPort() == -1 && "https".equalsIgnoreCase(uri.getScheme())
      ? 443 : uri.getPort();
  }

  @Override
  public void onConfigurationChanged(android.content.res.Configuration configuration) {
    super.onConfigurationChanged(configuration);
    web.requestLayout();
    web.invalidate();
  }

  @Override
  protected void onSaveInstanceState(Bundle state) {
    web.saveState(state);
    state.putString("lastUrl", web.getUrl());
    super.onSaveInstanceState(state);
  }

  private void syncNotifications() {
    String cookie = CookieManager.getInstance().getCookie(base);
    java.util.regex.Matcher session = java.util.regex.Pattern.compile(
      "(?:^|;\\s*)(sessionid=[^;]+)(?:;|$)"
    ).matcher(cookie == null ? "" : cookie);
    boolean loggedIn = session.find();
    if (loggedIn) cookie = session.group(1);
    Intent service = new Intent(this, NotificationService.class);
    if (!loggedIn) {
      stopService(service);
      return;
    }
    if (
      android.os.Build.VERSION.SDK_INT >= 33 &&
      checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) !=
        PackageManager.PERMISSION_GRANTED
    ) return;
    service.putExtra("cookie", cookie);
    try {
      startForegroundService(service);
    } catch (RuntimeException error) {
      Toast.makeText(
        this,
        "Не вдалося запустити сповіщення. Відкрийте додаток повторно.",
        Toast.LENGTH_LONG
      ).show();
    }
  }

  private void openNotification(Intent intent) {
    String path = intent.getStringExtra("path");
    if (
      path == null ||
      !path.startsWith("/") ||
      path.startsWith("//") ||
      path.contains("\\")
    ) path = "/";
    web.loadUrl(base + path);
  }

  @Override
  protected void onNewIntent(Intent intent) {
    super.onNewIntent(intent);
    setIntent(intent);
    if (intent.hasExtra("path")) openNotification(intent);
  }

  @Override
  public void onRequestPermissionsResult(
    int request,
    String[] permissions,
    int[] results
  ) {
    super.onRequestPermissionsResult(request, permissions, results);
    if (request == MICROPHONE && microphoneRequest != null) {
      PermissionRequest pending = microphoneRequest;
      microphoneRequest = null;
      if (results.length > 0 && results[0] == PackageManager.PERMISSION_GRANTED &&
          sameServer(pending.getOrigin()) &&
          sameServer(Uri.parse(web.getUrl() == null ? "" : web.getUrl()))) {
        pending.grant(new String[] { PermissionRequest.RESOURCE_AUDIO_CAPTURE });
      } else {
        pending.deny();
        Toast.makeText(this,
          "Дозвольте мікрофон у налаштуваннях Android → Додатки → SessionLender → Дозволи.",
          Toast.LENGTH_LONG).show();
      }
    }
    if (
      request == 77 &&
      results.length > 0 &&
      results[0] == PackageManager.PERMISSION_GRANTED
    ) syncNotifications();
  }

  @Override
  protected void onResume() {
    super.onResume();
    if (web != null) syncNotifications();
  }

  @Override
  protected void onActivityResult(int request, int result, Intent data) {
    super.onActivityResult(request, result, data);
    if (request == PICK_FILE && files != null) {
      files.onReceiveValue(
        WebChromeClient.FileChooserParams.parseResult(result, data)
      );
      files = null;
    }
  }

  @Override
  public void onBackPressed() {
    if (web.canGoBack()) web.goBack();
    else super.onBackPressed();
  }

  @Override
  protected void onDestroy() {
    if (files != null) files.onReceiveValue(null);
    cancelMicrophoneRequest();
    web.destroy();
    super.onDestroy();
  }
}
