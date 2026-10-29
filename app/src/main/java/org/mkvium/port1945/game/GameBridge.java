package org.mkvium.port1945.game;

/** JNI boundary for the explicitly labelled native prototype. */
public final class GameBridge {
    static {
        System.loadLibrary("portcore");
    }

    private GameBridge() { }

    public static native void nativeInitGame();
    public static native void nativeSurfaceCreated();
    public static native void nativeSurfaceChanged(int width, int height);
    public static native void nativeFrame(float deltaSeconds, float moveX, float moveY,
                                          boolean fireDown, boolean pausePressed);
    public static native void nativePauseForLifecycle();
    public static native void nativeInitAudio();
    public static native void nativeMixAudio(short[] output);
}
