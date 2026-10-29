package android.view;
public class KeyEvent {
    public static final int ACTION_UP = 1;
    public static final int KEYCODE_A = 29, KEYCODE_D = 32, KEYCODE_W = 51, KEYCODE_S = 47;
    public static final int KEYCODE_DPAD_LEFT = 21, KEYCODE_DPAD_RIGHT = 22;
    public static final int KEYCODE_DPAD_UP = 19, KEYCODE_DPAD_DOWN = 20;
    public static final int KEYCODE_BUTTON_A = 96, KEYCODE_BUTTON_START = 108;
    public static final int KEYCODE_SPACE = 62, KEYCODE_J = 38, KEYCODE_ESCAPE = 111, KEYCODE_BACK = 4;
    private final int keyCode;
    private final int action;
    public KeyEvent(int action, int keyCode) { this.action = action; this.keyCode = keyCode; }
    public InputDevice getDevice() { return new InputDevice(1); }
    public int getAction() { return action; }
    public int getKeyCode() { return keyCode; }
    public int getScanCode() { return 0; }
    public int getRepeatCount() { return 0; }
    public int getSource() { return 0; }
    public static String keyCodeToString(int keyCode) { return Integer.toString(keyCode); }
}
