package android.widget;
import android.content.Context;
import android.view.View;
import android.view.ViewGroup;
public class FrameLayout extends ViewGroup {
    public FrameLayout(Context context) { super(context); }
    public void setBackgroundColor(int color) { }
    @Override public void addView(View view) { }
    @Override public void addView(View view, ViewGroup.LayoutParams params) { }
    public static class LayoutParams extends ViewGroup.LayoutParams {
        public LayoutParams(int width, int height) { super(width, height); }
        public int leftMargin;
        public int topMargin;
        public LayoutParams(int width, int height, int gravity) { super(width, height); }
    }
}
