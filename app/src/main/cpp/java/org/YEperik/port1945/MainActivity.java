package org.mkvium.port1945;

import android.app.Activity;
import android.hardware.input.InputManager;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.InputDevice;
import android.view.KeyEvent;
import android.view.MotionEvent;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import java.util.ArrayDeque;
import java.util.Locale;

/** Build/diagnostic shell only. It does not run original game code or render gameplay. */
public final class MainActivity extends Activity implements InputManager.InputDeviceListener {
    private static final int MAX_LOG_LINES = 70;
    private static final int[] AXIS_CODES = {
        MotionEvent.AXIS_X, MotionEvent.AXIS_Y,
        MotionEvent.AXIS_Z, MotionEvent.AXIS_RZ,
        MotionEvent.AXIS_RX, MotionEvent.AXIS_RY,
        MotionEvent.AXIS_HAT_X, MotionEvent.AXIS_HAT_Y,
        MotionEvent.AXIS_LTRIGGER, MotionEvent.AXIS_RTRIGGER
    };

    private final ArrayDeque<String> lines = new ArrayDeque<>();
    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private InputManager inputManager;
    private TextView statusView;
    private TextView snapshotView;
    private TextView eventView;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        NativeInputBridge.nativeInit();
        inputManager = (InputManager) getSystemService(INPUT_SERVICE);
        buildUi();
        appendLine("App started. This is a CI/input-probe scaffold, not playable gameplay.");
        appendLine(NativeInputBridge.nativeVersion());
        refreshInputDevices();
    }

    private void buildUi() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(18), dp(18), dp(18), dp(18));

        TextView title = new TextView(this);
        title.setText("1945 Native Port");
        title.setTextSize(24f);
        title.setPadding(0, 0, 0, dp(8));
        root.addView(title);

        TextView note = new TextView(this);
        note.setText("GitHub Actions build scaffold · native input diagnostics only\nNo game assets, original executable, or gameplay runtime are bundled.");
        note.setTextSize(14f);
        root.addView(note);

        statusView = new TextView(this);
        statusView.setTextSize(15f);
        statusView.setPadding(0, dp(14), 0, dp(8));
        root.addView(statusView);

        snapshotView = new TextView(this);
        snapshotView.setTextSize(13f);
        snapshotView.setPadding(0, 0, 0, dp(12));
        root.addView(snapshotView);

        TextView caption = new TextView(this);
        caption.setText("Raw controller events (no default button mapping)");
        caption.setTextSize(16f);
        root.addView(caption);

        eventView = new TextView(this);
        eventView.setTextSize(12f);
        eventView.setTextIsSelectable(true);
        ScrollView scroll = new ScrollView(this);
        scroll.addView(eventView);
        LinearLayout.LayoutParams scrollParams = new LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f);
        scrollParams.topMargin = dp(8);
        root.addView(scroll, scrollParams);
        setContentView(root);
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (inputManager != null) {
            inputManager.registerInputDeviceListener(this, mainHandler);
        }
        refreshInputDevices();
    }

    @Override
    protected void onPause() {
        if (inputManager != null) {
            inputManager.unregisterInputDeviceListener(this);
        }
        NativeInputBridge.nativeSetConnected(false);
        refreshSnapshot();
        super.onPause();
    }

    @Override
    public boolean dispatchKeyEvent(KeyEvent event) {
        InputDevice device = event.getDevice();
        if (device != null && isControllerDevice(device)) {
            boolean down = event.getAction() != KeyEvent.ACTION_UP;
            NativeInputBridge.nativeOnKey(event.getKeyCode(), down);
            appendLine(String.format(Locale.ROOT,
                "%s device=%s id=%d keyCode=%d(%s) scan=%d repeat=%d source=0x%x",
                down ? "KEY_DOWN" : "KEY_UP", safeName(device), device.getId(),
                event.getKeyCode(), KeyEvent.keyCodeToString(event.getKeyCode()),
                event.getScanCode(), event.getRepeatCount(), event.getSource()));
            refreshSnapshot();
            return true;
        }
        return super.dispatchKeyEvent(event);
    }

    @Override
    public boolean dispatchGenericMotionEvent(MotionEvent event) {
        InputDevice device = event.getDevice();
        if (device != null && isControllerDevice(device) &&
                (event.getSource() & InputDevice.SOURCE_CLASS_JOYSTICK) != 0) {
            StringBuilder raw = new StringBuilder();
            raw.append("MOTION device=").append(safeName(device))
               .append(" id=").append(device.getId())
               .append(" source=0x").append(Integer.toHexString(event.getSource()));
            for (int axis : AXIS_CODES) {
                float value = event.getAxisValue(axis);
                NativeInputBridge.nativeOnAxis(axis, value);
                raw.append('\n').append("  axis ").append(axisName(axis))
                   .append("[").append(axis).append("]=")
                   .append(String.format(Locale.ROOT, "%.3f", value));
            }
            appendLine(raw.toString());
            refreshSnapshot();
            return true;
        }
        return super.dispatchGenericMotionEvent(event);
    }

    @Override
    public void onInputDeviceAdded(int deviceId) {
        refreshInputDevices();
        appendLine("Input device added: id=" + deviceId);
    }

    @Override
    public void onInputDeviceRemoved(int deviceId) {
        refreshInputDevices();
        appendLine("Input device removed: id=" + deviceId);
    }

    @Override
    public void onInputDeviceChanged(int deviceId) {
        refreshInputDevices();
        appendLine("Input device changed: id=" + deviceId);
    }

    private void refreshInputDevices() {
        if (inputManager == null) {
            return;
        }
        StringBuilder names = new StringBuilder();
        int count = 0;
        for (int id : inputManager.getInputDeviceIds()) {
            InputDevice device = inputManager.getInputDevice(id);
            if (device != null && isControllerDevice(device)) {
                if (count > 0) names.append("\n");
                names.append("• ").append(safeName(device)).append(" (id ").append(id).append(")");
                count++;
            }
        }
        NativeInputBridge.nativeSetConnected(count > 0);
        if (statusView != null) {
            statusView.setText("Controller devices detected: " + count +
                (count == 0 ? "\nConnect a controller to inspect raw events." : "\n" + names));
        }
        refreshSnapshot();
    }

    private void refreshSnapshot() {
        if (snapshotView == null) return;
        int[] s = NativeInputBridge.nativeSnapshot();
        if (s == null || s.length < 11) {
            snapshotView.setText("Native input state unavailable.");
            return;
        }
        snapshotView.setText(String.format(Locale.ROOT,
            "Native model (numeric masks only)\nconnected=%d current=0x%04x previous=0x%04x pressedEdges=0x%04x\n" +
            "axisDirections=0x%04x previousDirections=0x%04x directionEdges=0x%04x\n" +
            "A=(%d,%d) B=(%d,%d)\nConfigured bindings: none by default",
            s[0], s[1], s[2], s[3], s[4], s[5], s[6], s[7], s[8], s[9], s[10]));
    }

    private void appendLine(String line) {
        lines.addLast(line);
        while (lines.size() > MAX_LOG_LINES) lines.removeFirst();
        if (eventView != null) {
            StringBuilder text = new StringBuilder();
            for (String item : lines) text.append(item).append("\n\n");
            eventView.setText(text.toString());
        }
    }

    private static boolean isControllerDevice(InputDevice device) {
        int sources = device.getSources();
        return (sources & InputDevice.SOURCE_GAMEPAD) == InputDevice.SOURCE_GAMEPAD ||
               (sources & InputDevice.SOURCE_JOYSTICK) == InputDevice.SOURCE_JOYSTICK;
    }

    private static String safeName(InputDevice device) {
        return device.getName() == null ? "unnamed" : device.getName();
    }

    private static String axisName(int axis) {
        switch (axis) {
            case MotionEvent.AXIS_X: return "X";
            case MotionEvent.AXIS_Y: return "Y";
            case MotionEvent.AXIS_Z: return "Z";
            case MotionEvent.AXIS_RZ: return "RZ";
            case MotionEvent.AXIS_RX: return "RX";
            case MotionEvent.AXIS_RY: return "RY";
            case MotionEvent.AXIS_HAT_X: return "HAT_X";
            case MotionEvent.AXIS_HAT_Y: return "HAT_Y";
            case MotionEvent.AXIS_LTRIGGER: return "LTRIGGER";
            case MotionEvent.AXIS_RTRIGGER: return "RTRIGGER";
            default: return "axis";
        }
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }
}
