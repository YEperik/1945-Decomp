package org.mkvium.port1945;

/** JNI bridge for the host-tested portable input core. No physical button mapping is assumed. */
public final class NativeInputBridge {
    static {
        System.loadLibrary("portcore");
    }

    private NativeInputBridge() { }

    public static native String nativeVersion();
    public static native void nativeInit();
    public static native boolean nativeBindKey(int androidKeyCode, int numericOutputMask);
    public static native boolean nativeBindAxis(int androidAxisCode, int numericAxisTarget);
    public static native boolean nativeBindHatAxis(int androidAxisCode,
                                                   int negativeNumericMask,
                                                   int positiveNumericMask);
    public static native void nativeSetConnected(boolean connected);
    public static native boolean nativeOnKey(int androidKeyCode, boolean down);
    public static native boolean nativeOnAxis(int androidAxisCode, float normalizedValue);
    /** connected, currentMask, previousMask, pressedEdges, currentDirs, previousDirs, dirEdges, A-X, A-Y, B-X, B-Y */
    public static native int[] nativeSnapshot();
}
