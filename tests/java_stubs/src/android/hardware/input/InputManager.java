package android.hardware.input;
import android.os.Handler;
public class InputManager {
    public interface InputDeviceListener {
        void onInputDeviceAdded(int deviceId);
        void onInputDeviceRemoved(int deviceId);
        void onInputDeviceChanged(int deviceId);
    }
    public int[] getInputDeviceIds() { return new int[0]; }
    public android.view.InputDevice getInputDevice(int id) { return null; }
    public void registerInputDeviceListener(InputDeviceListener listener, Handler handler) { }
    public void unregisterInputDeviceListener(InputDeviceListener listener) { }
}
