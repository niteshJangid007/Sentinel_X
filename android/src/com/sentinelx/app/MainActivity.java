package com.sentinelx.app;

import android.app.Activity;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.view.View;
import android.view.inputmethod.InputMethodManager;
import android.webkit.CookieManager;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.PopupMenu;
import android.widget.TextView;
import android.widget.Toast;

/**
 * Thin Android client for a SentinelX desktop instance.
 *
 * <p>The desktop app owns the data; this app shows the same dashboard full
 * screen and remembers which server it belongs to. It works against the local
 * Wi-Fi address or the public https:// link the desktop app prints.
 */
public class MainActivity extends Activity {

    private static final String PREFS = "sentinelx";
    private static final String KEY_URL = "server_url";
    private static final int FILE_CHOOSER = 1001;

    private WebView web;
    private LinearLayout setup;
    private EditText input;
    private TextView menuButton;
    private SharedPreferences prefs;
    private ValueCallback<Uri[]> pendingFiles;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        setContentView(R.layout.activity_main);

        prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
        web = findViewById(R.id.web);
        setup = findViewById(R.id.setup);
        input = findViewById(R.id.url);
        menuButton = findViewById(R.id.menu_button);
        Button connect = findViewById(R.id.connect);

        WebSettings settings = web.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setUseWideViewPort(true);
        settings.setLoadWithOverviewMode(true);
        settings.setBuiltInZoomControls(false);
        settings.setDisplayZoomControls(false);
        settings.setMediaPlaybackRequiresUserGesture(true);
        settings.setUserAgentString(settings.getUserAgentString() + " SentinelXApp/1.0");

        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(web, false);

        web.setBackgroundColor(Color.parseColor("#06080D"));
        web.setWebViewClient(new WebViewClient() {
            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) {
                    Toast.makeText(MainActivity.this,
                            "Cannot reach the server. Check the address and that the desktop app is running.",
                            Toast.LENGTH_LONG).show();
                }
            }
        });
        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback,
                    FileChooserParams params) {
                pendingFiles = callback;
                Intent intent = new Intent(Intent.ACTION_GET_CONTENT);
                intent.addCategory(Intent.CATEGORY_OPENABLE);
                intent.setType("*/*");
                try {
                    startActivityForResult(Intent.createChooser(intent, "Select project ZIP"), FILE_CHOOSER);
                } catch (Exception error) {
                    pendingFiles = null;
                    return false;
                }
                return true;
            }
        });

        connect.setOnClickListener(view -> {
            String value = input.getText().toString().trim();
            if (value.isEmpty()) {
                Toast.makeText(this, "Enter the address shown in the desktop app", Toast.LENGTH_SHORT).show();
                return;
            }
            open(value);
        });

        menuButton.setOnClickListener(view -> {
            PopupMenu menu = new PopupMenu(this, menuButton);
            menu.getMenu().add(0, 1, 0, R.string.reload);
            menu.getMenu().add(0, 2, 1, R.string.change_server);
            menu.setOnMenuItemClickListener(item -> {
                if (item.getItemId() == 1) {
                    web.reload();
                    return true;
                }
                if (item.getItemId() == 2) {
                    showSetup();
                    return true;
                }
                return false;
            });
            menu.show();
        });

        String saved = prefs.getString(KEY_URL, "");
        if (!saved.isEmpty()) {
            input.setText(saved);
            open(saved);
        }
    }

    private void open(String raw) {
        String url = normalize(raw);
        prefs.edit().putString(KEY_URL, url).apply();
        input.setText(url);
        setup.setVisibility(View.GONE);
        web.setVisibility(View.VISIBLE);
        menuButton.setVisibility(View.VISIBLE);
        web.loadUrl(url);
        hideKeyboard();
    }

    private String normalize(String raw) {
        String value = raw.trim();
        if (!value.startsWith("http://") && !value.startsWith("https://")) {
            value = "http://" + value;
        }
        while (value.endsWith("/")) {
            value = value.substring(0, value.length() - 1);
        }
        return value;
    }

    private void showSetup() {
        web.setVisibility(View.GONE);
        menuButton.setVisibility(View.GONE);
        setup.setVisibility(View.VISIBLE);
        input.requestFocus();
    }

    private void hideKeyboard() {
        InputMethodManager manager = (InputMethodManager) getSystemService(INPUT_METHOD_SERVICE);
        if (manager != null) {
            manager.hideSoftInputFromWindow(input.getWindowToken(), 0);
        }
    }

    @Override
    public void onBackPressed() {
        if (web.getVisibility() == View.VISIBLE && web.canGoBack()) {
            web.goBack();
            return;
        }
        if (web.getVisibility() == View.VISIBLE) {
            showSetup();
            return;
        }
        super.onBackPressed();
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        if (requestCode == FILE_CHOOSER) {
            Uri[] result = null;
            if (resultCode == RESULT_OK && data != null && data.getData() != null) {
                result = new Uri[] {data.getData()};
            }
            if (pendingFiles != null) {
                pendingFiles.onReceiveValue(result);
                pendingFiles = null;
            }
            return;
        }
        super.onActivityResult(requestCode, resultCode, data);
    }

    @Override
    protected void onDestroy() {
        if (web != null) {
            web.destroy();
        }
        super.onDestroy();
    }
}
