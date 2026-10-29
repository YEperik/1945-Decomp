package android.view;
public class MotionEvent {
    public static final int INVALID_POINTER_ID = -1;
    public static final int ACTION_DOWN = 0, ACTION_UP = 1, ACTION_MOVE = 2;
    public static final int ACTION_CANCEL = 3, ACTION_POINTER_DOWN = 5, ACTION_POINTER_UP = 6;
    public static final int AXIS_X = 0, AXIS_Y = 1, AXIS_Z = 11, AXIS_RZ = 14;
    public static final int AXIS_RX = 12, AXIS_RY = 13, AXIS_HAT_X = 15, AXIS_HAT_Y = 16;
    public static final int AXIS_LTRIGGER = 17, AXIS_RTRIGGER = 18;
    private final int action;
    public MotionEvent(int action) { this.action = action; }
    public int getActionMasked() { return action; }
    public int getActionIndex() { return 0; }
    public int getPointerCount() { return 1; }
    public int getPointerId(int index) { return 0; }
    public float getX(int index) { return 0.0f; }
    public float getY(int index) { return 0.0f; }
    public float getAxisValue(int axis) { return 0.0f; }
    public InputDevice getDevice() { return new InputDevice(1); }
    public int getSource() { return InputDevice.SOURCE_JOYSTICK; }
}
