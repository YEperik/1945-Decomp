package android.view;
import android.content.Context;
public class ViewGroup extends View {
    public ViewGroup(Context context) { super(context); }
    public void addView(View view) { }
    public void addView(View view, LayoutParams params) { }
    public static class LayoutParams {
        public static final int MATCH_PARENT = -1;
        public static final int WRAP_CONTENT = -2;
        public int width;
        public int height;
        public LayoutParams(int width, int height) { this.width = width; this.height = height; }
    }
}
