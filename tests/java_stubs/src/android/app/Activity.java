package android.app;
import android.content.Context;
import android.content.Intent;
import android.os.Bundle;
import android.view.KeyEvent;
import android.view.MotionEvent;
import android.view.View;
import android.view.Window;
public class Activity extends Context {
    protected void onCreate(Bundle state) { }
    protected void onResume() { }
    protected void onPause() { }
    protected void onDestroy() { }
    public Window getWindow() { return new Window(); }
    public void setContentView(View view) { }
    public void startActivity(Intent intent) { }
    public boolean dispatchKeyEvent(KeyEvent event) { return false; }
    public boolean dispatchGenericMotionEvent(MotionEvent event) { return false; }
}
