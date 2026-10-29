package org.mkvium.port1945.game;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Color;
import android.hardware.input.InputManager;
import android.os.Bundle;
import android.view.Gravity;
import android.view.InputDevice;
import android.view.View;
import android.widget.FrameLayout;
import android.widget.TextView;

import org.mkvium.port1945.MainActivity;

/** Launcher for the explicit native gameplay/render/audio prototype, not an original-game port yet. */
public final class GameActivity extends Activity implements InputManager.InputDeviceListener {
    private GameSurfaceView gameView;
    private GameAudio gameAudio;
    private InputManager inputManager;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().getDecorView().setSystemUiVisibility(
            View.SYSTEM_UI_FLAG_FULLSCREEN | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION |
            View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY | View.SYSTEM_UI_FLAG_LAYOUT_STABLE);
        GameBridge.nativeInitGame();
        gameAudio = new GameAudio();
        inputManager = (InputManager) getSystemService(INPUT_SERVICE);
        gameView = new GameSurfaceView(this);

        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(Color.BLACK);
        root.addView(gameView, new FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT));

        TextView inputButton = new TextView(this);
        inputButton.setText("INPUT");
        inputButton.setTextColor(Color.WHITE);
        inputButton.setTextSize(12.0f);
        inputButton.setGravity(Gravity.CENTER);
        inputButton.setPadding(dp(10), dp(6), dp(10), dp(6));
        inputButton.setBackgroundColor(0xCC18304A);
        inputButton.setContentDescription("Open input diagnostic screen");
        inputButton.setOnClickListener(view -> startActivity(new Intent(this, MainActivity.class)));
        FrameLayout.LayoutParams buttonParams = new FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.WRAP_CONTENT, FrameLayout.LayoutParams.WRAP_CONTENT,
            Gravity.TOP | Gravity.LEFT);
        buttonParams.leftMargin = dp(8);
        buttonParams.topMargin = dp(8);
        root.addView(inputButton, buttonParams);
        setContentView(root);
        gameView.requestFocus();
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (inputManager != null) inputManager.registerInputDeviceListener(this, null);
        if (gameView != null) gameView.onResume();
        if (gameAudio != null) gameAudio.start();
    }

    @Override
    protected void onPause() {
        if (inputManager != null) inputManager.unregisterInputDeviceListener(this);
        if (gameView != null) {
            gameView.clearAllInput();
            gameView.onPause();
        }
        GameBridge.nativePauseForLifecycle();
        if (gameAudio != null) gameAudio.stop();
        super.onPause();
    }

    @Override
    protected void onDestroy() {
        if (gameAudio != null) gameAudio.stop();
        super.onDestroy();
    }

    @Override
    public void onInputDeviceAdded(int deviceId) {
        // The view chooses one active controller when the first event arrives.
    }

    @Override
    public void onInputDeviceChanged(int deviceId) {
        InputDevice device = InputDevice.getDevice(deviceId);
        if (device == null) onInputDeviceRemoved(deviceId);
    }

    @Override
    public void onInputDeviceRemoved(int deviceId) {
        if (gameView != null) gameView.onControllerRemoved(deviceId);
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }
}
