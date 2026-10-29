package android.view;
public class InputDevice {
    public static final int SOURCE_CLASS_JOYSTICK = 0x10;
    public static final int SOURCE_GAMEPAD = 0x401;
    public static final int SOURCE_JOYSTICK = 0x1000010;
    private final int id;
    public InputDevice(int id) { this.id = id; }
    public int getSources() { return SOURCE_GAMEPAD; }
    public String getName() { return "stub"; }
    public int getId() { return id; }
    public static InputDevice getDevice(int id) { return null; }
}
