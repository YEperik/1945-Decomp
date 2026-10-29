package android.view;
import android.content.Context;
import android.content.res.Resources;
public class View {
    public static final int SYSTEM_UI_FLAG_FULLSCREEN = 4;
    public static final int SYSTEM_UI_FLAG_HIDE_NAVIGATION = 2;
    public static final int SYSTEM_UI_FLAG_IMMERSIVE_STICKY = 4096;
    public static final int SYSTEM_UI_FLAG_LAYOUT_STABLE = 256;
    private final Context context;
    private int width = 320;
    private int height = 240;
    public interface OnClickListener { void onClick(View view); }
    public View(Context context) { this.context = context; }
    public void setSystemUiVisibility(int flags) { }
    public void setKeepScreenOn(boolean keepScreenOn) { }
    public void setFocusable(boolean focusable) { }
    public void setFocusableInTouchMode(boolean focusable) { }
    public void setContentDescription(CharSequence description) { }
    public void setOnClickListener(OnClickListener listener) { }
    public Resources getResources() { return context == null ? new Resources() : context.getResources(); }
    public int getWidth() { return width; }
    public int getHeight() { return height; }
    public void requestFocus() { }
    public boolean performClick() { return true; }
    public boolean onTouchEvent(MotionEvent event) { return false; }
    public boolean onKeyDown(int keyCode, KeyEvent event) { return false; }
    public boolean onKeyUp(int keyCode, KeyEvent event) { return false; }
    public boolean onGenericMotionEvent(MotionEvent event) { return false; }
}
