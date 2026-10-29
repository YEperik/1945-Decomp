package android.widget;
import android.content.Context;
import android.view.View;
import android.view.ViewGroup;
public class LinearLayout extends ViewGroup {
    public static final int VERTICAL = 1, HORIZONTAL = 0;
    public LinearLayout(Context context) { super(context); }
    public void setOrientation(int orientation) { }
    public void setPadding(int left, int top, int right, int bottom) { }
    @Override public void addView(View view) { }
    @Override public void addView(View view, ViewGroup.LayoutParams params) { }
    public static class LayoutParams extends ViewGroup.LayoutParams {
        public int topMargin;
        public LayoutParams(int width, int height, float weight) { super(width, height); }
    }
}
