package org.mkvium.port1945.game;

import android.content.Context;
import android.opengl.GLSurfaceView;
import android.view.InputDevice;
import android.view.KeyEvent;
import android.view.MotionEvent;

import java.util.concurrent.atomic.AtomicBoolean;

/** GLES2 host view. Touch/gamepad input is prototype mapping, not the PS2 game's verified mapping. */
public final class GameSurfaceView extends GLSurfaceView implements GLSurfaceView.Renderer {
    private static final float TOUCH_STICK_X = 58.0f;
    private static final float TOUCH_STICK_Y = 193.0f;
    private static final float TOUCH_STICK_RADIUS = 34.0f;

    private final AtomicBoolean pauseRequested = new AtomicBoolean(false);
    private volatile float touchMoveX;
    private volatile float touchMoveY;
    private volatile boolean touchFire;
    private volatile boolean keyLeft;
    private volatile boolean keyRight;
    private volatile boolean keyUp;
    private volatile boolean keyDown;
    private volatile boolean keyboardFire;
    private volatile float controllerMoveX;
    private volatile float controllerMoveY;
    private volatile boolean controllerLeft;
    private volatile boolean controllerRight;
    private volatile boolean controllerUp;
    private volatile boolean controllerDown;
    private volatile boolean controllerFire;
    private volatile int activeControllerId = -1;
    private int movementPointerId = MotionEvent.INVALID_POINTER_ID;
    private int firePointerId = MotionEvent.INVALID_POINTER_ID;
    private long lastFrameNanos;

    public GameSurfaceView(Context context) {
        super(context);
        setEGLContextClientVersion(2);
        setPreserveEGLContextOnPause(true);
        setRenderer(this);
        setRenderMode(GLSurfaceView.RENDERMODE_CONTINUOUSLY);
        setFocusable(true);
        setFocusableInTouchMode(true);
        setKeepScreenOn(true);
        setContentDescription("1945 Native gameplay prototype. Touch left to steer, right to fire, top right to pause.");
    }

    @Override
    public void onSurfaceCreated(javax.microedition.khronos.opengles.GL10 unused,
                                 javax.microedition.khronos.egl.EGLConfig config) {
        GameBridge.nativeSurfaceCreated();
        lastFrameNanos = 0L;
    }

    @Override
    public void onSurfaceChanged(javax.microedition.khronos.opengles.GL10 unused,
                                 int width, int height) {
        GameBridge.nativeSurfaceChanged(width, height);
    }

    @Override
    public void onDrawFrame(javax.microedition.khronos.opengles.GL10 unused) {
        long now = System.nanoTime();
        float delta = lastFrameNanos == 0L
            ? (1.0f / 60.0f)
            : (float) ((double) (now - lastFrameNanos) / 1_000_000_000.0);
        lastFrameNanos = now;
        if (!Float.isFinite(delta) || delta < 0.0f) {
            delta = 1.0f / 60.0f;
        }
        if (delta > 0.25f) {
            delta = 0.25f;
        }
        float x = (keyRight ? 1.0f : 0.0f) - (keyLeft ? 1.0f : 0.0f);
        float y = (keyDown ? 1.0f : 0.0f) - (keyUp ? 1.0f : 0.0f);
        x += touchMoveX + controllerMoveX + (controllerRight ? 1.0f : 0.0f) -
             (controllerLeft ? 1.0f : 0.0f);
        y += touchMoveY + controllerMoveY + (controllerDown ? 1.0f : 0.0f) -
             (controllerUp ? 1.0f : 0.0f);
        x = clamp(x);
        y = clamp(y);
        boolean fire = touchFire || keyboardFire || controllerFire;
        boolean pause = pauseRequested.getAndSet(false);
        GameBridge.nativeFrame(delta, x, y, fire, pause);
    }

    public void clearAllInput() {
        touchMoveX = 0.0f;
        touchMoveY = 0.0f;
        touchFire = false;
        keyLeft = false;
        keyRight = false;
        keyUp = false;
        keyDown = false;
        keyboardFire = false;
        controllerMoveX = 0.0f;
        controllerMoveY = 0.0f;
        controllerLeft = false;
        controllerRight = false;
        controllerUp = false;
        controllerDown = false;
        controllerFire = false;
        movementPointerId = MotionEvent.INVALID_POINTER_ID;
        firePointerId = MotionEvent.INVALID_POINTER_ID;
        pauseRequested.set(false);
    }

    public void onControllerRemoved(int deviceId) {
        if (activeControllerId == deviceId) {
            activeControllerId = -1;
            controllerMoveX = 0.0f;
            controllerMoveY = 0.0f;
            controllerLeft = false;
            controllerRight = false;
            controllerUp = false;
            controllerDown = false;
            controllerFire = false;
        }
    }

    @Override
    public boolean onTouchEvent(MotionEvent event) {
        int action = event.getActionMasked();
        if (action == MotionEvent.ACTION_DOWN || action == MotionEvent.ACTION_POINTER_DOWN) {
            int index = event.getActionIndex();
            float[] logical = toLogical(event.getX(index), event.getY(index));
            float x = logical[0];
            float y = logical[1];
            if (x >= 260.0f && y <= 42.0f) {
                pauseRequested.set(true);
            } else if (x < 150.0f && y > 120.0f && movementPointerId == MotionEvent.INVALID_POINTER_ID) {
                movementPointerId = event.getPointerId(index);
                updateMovement(x, y);
            } else if (x > 220.0f && y > 130.0f && firePointerId == MotionEvent.INVALID_POINTER_ID) {
                firePointerId = event.getPointerId(index);
                touchFire = true;
            }
            return true;
        }
        if (action == MotionEvent.ACTION_MOVE) {
            for (int i = 0; i < event.getPointerCount(); i++) {
                int pointerId = event.getPointerId(i);
                float[] logical = toLogical(event.getX(i), event.getY(i));
                if (pointerId == movementPointerId) {
                    updateMovement(logical[0], logical[1]);
                } else if (pointerId == firePointerId) {
                    touchFire = logical[0] > 195.0f && logical[1] > 112.0f;
                }
            }
            return true;
        }
        if (action == MotionEvent.ACTION_UP || action == MotionEvent.ACTION_POINTER_UP ||
                action == MotionEvent.ACTION_CANCEL) {
            if (action == MotionEvent.ACTION_CANCEL) {
                clearAllInput();
                return true;
            }
            int index = event.getActionIndex();
            int pointerId = event.getPointerId(index);
            if (pointerId == movementPointerId) {
                movementPointerId = MotionEvent.INVALID_POINTER_ID;
                touchMoveX = 0.0f;
                touchMoveY = 0.0f;
            }
            if (pointerId == firePointerId) {
                firePointerId = MotionEvent.INVALID_POINTER_ID;
                touchFire = false;
            }
            if (action == MotionEvent.ACTION_UP) {
                performClick();
            }
            return true;
        }
        return true;
    }

    @Override
    public boolean performClick() {
        super.performClick();
        return true;
    }

    @Override
    public boolean onKeyDown(int keyCode, KeyEvent event) {
        InputDevice device = event.getDevice();
        if (device != null && isController(device)) {
            if (!acceptController(device.getId())) return true;
            switch (keyCode) {
                case KeyEvent.KEYCODE_DPAD_LEFT: controllerLeft = true; return true;
                case KeyEvent.KEYCODE_DPAD_RIGHT: controllerRight = true; return true;
                case KeyEvent.KEYCODE_DPAD_UP: controllerUp = true; return true;
                case KeyEvent.KEYCODE_DPAD_DOWN: controllerDown = true; return true;
                case KeyEvent.KEYCODE_BUTTON_A: controllerFire = true; return true;
                case KeyEvent.KEYCODE_BUTTON_START:
                    if (event.getRepeatCount() == 0) pauseRequested.set(true);
                    return true;
                default: return super.onKeyDown(keyCode, event);
            }
        }
        switch (keyCode) {
            case KeyEvent.KEYCODE_A:
            case KeyEvent.KEYCODE_DPAD_LEFT: keyLeft = true; return true;
            case KeyEvent.KEYCODE_D:
            case KeyEvent.KEYCODE_DPAD_RIGHT: keyRight = true; return true;
            case KeyEvent.KEYCODE_W:
            case KeyEvent.KEYCODE_DPAD_UP: keyUp = true; return true;
            case KeyEvent.KEYCODE_S:
            case KeyEvent.KEYCODE_DPAD_DOWN: keyDown = true; return true;
            case KeyEvent.KEYCODE_SPACE:
            case KeyEvent.KEYCODE_J: keyboardFire = true; return true;
            case KeyEvent.KEYCODE_ESCAPE:
            case KeyEvent.KEYCODE_BACK:
                if (event.getRepeatCount() == 0) pauseRequested.set(true);
                return true;
            default: return super.onKeyDown(keyCode, event);
        }
    }

    @Override
    public boolean onKeyUp(int keyCode, KeyEvent event) {
        InputDevice device = event.getDevice();
        if (device != null && isController(device)) {
            if (device.getId() != activeControllerId) return true;
            switch (keyCode) {
                case KeyEvent.KEYCODE_DPAD_LEFT: controllerLeft = false; return true;
                case KeyEvent.KEYCODE_DPAD_RIGHT: controllerRight = false; return true;
                case KeyEvent.KEYCODE_DPAD_UP: controllerUp = false; return true;
                case KeyEvent.KEYCODE_DPAD_DOWN: controllerDown = false; return true;
                case KeyEvent.KEYCODE_BUTTON_A: controllerFire = false; return true;
                default: return super.onKeyUp(keyCode, event);
            }
        }
        switch (keyCode) {
            case KeyEvent.KEYCODE_A:
            case KeyEvent.KEYCODE_DPAD_LEFT: keyLeft = false; return true;
            case KeyEvent.KEYCODE_D:
            case KeyEvent.KEYCODE_DPAD_RIGHT: keyRight = false; return true;
            case KeyEvent.KEYCODE_W:
            case KeyEvent.KEYCODE_DPAD_UP: keyUp = false; return true;
            case KeyEvent.KEYCODE_S:
            case KeyEvent.KEYCODE_DPAD_DOWN: keyDown = false; return true;
            case KeyEvent.KEYCODE_SPACE:
            case KeyEvent.KEYCODE_J: keyboardFire = false; return true;
            default: return super.onKeyUp(keyCode, event);
        }
    }

    @Override
    public boolean onGenericMotionEvent(MotionEvent event) {
        InputDevice device = event.getDevice();
        if (device == null || !isController(device) ||
                (event.getSource() & InputDevice.SOURCE_CLASS_JOYSTICK) == 0) {
            return super.onGenericMotionEvent(event);
        }
        if (!acceptController(device.getId())) return true;
        float x = deadzone(event.getAxisValue(MotionEvent.AXIS_X));
        float y = deadzone(event.getAxisValue(MotionEvent.AXIS_Y));
        float hatX = deadzone(event.getAxisValue(MotionEvent.AXIS_HAT_X));
        float hatY = deadzone(event.getAxisValue(MotionEvent.AXIS_HAT_Y));
        controllerMoveX = Math.abs(x) >= 0.01f ? x : hatX;
        controllerMoveY = Math.abs(y) >= 0.01f ? y : hatY;
        return true;
    }

    private boolean acceptController(int deviceId) {
        if (activeControllerId == -1) {
            activeControllerId = deviceId;
        }
        return activeControllerId == deviceId;
    }

    private void updateMovement(float x, float y) {
        touchMoveX = clamp((x - TOUCH_STICK_X) / TOUCH_STICK_RADIUS);
        touchMoveY = clamp((y - TOUCH_STICK_Y) / TOUCH_STICK_RADIUS);
        float length = (float) Math.sqrt(touchMoveX * touchMoveX + touchMoveY * touchMoveY);
        if (length > 1.0f) {
            touchMoveX /= length;
            touchMoveY /= length;
        }
    }

    private float[] toLogical(float viewX, float viewY) {
        float scale = Math.min(getWidth() / 320.0f, getHeight() / 240.0f);
        if (scale <= 0.0f) scale = 1.0f;
        float offsetX = (getWidth() - 320.0f * scale) * 0.5f;
        float offsetY = (getHeight() - 240.0f * scale) * 0.5f;
        return new float[]{(viewX - offsetX) / scale, (viewY - offsetY) / scale};
    }

    private static float clamp(float value) {
        if (!Float.isFinite(value)) return 0.0f;
        return Math.max(-1.0f, Math.min(1.0f, value));
    }

    private static float deadzone(float value) {
        if (!Float.isFinite(value) || Math.abs(value) < 0.18f) return 0.0f;
        return clamp(value);
    }

    private static boolean isController(InputDevice device) {
        int sources = device.getSources();
        return (sources & InputDevice.SOURCE_GAMEPAD) == InputDevice.SOURCE_GAMEPAD ||
               (sources & InputDevice.SOURCE_JOYSTICK) == InputDevice.SOURCE_JOYSTICK;
    }
}
