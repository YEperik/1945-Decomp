package android.content;
import android.content.res.Resources;
public class Context {
    public static final String INPUT_SERVICE = "input";
    private final Resources resources = new Resources();
    public Object getSystemService(String name) { return null; }
    public Resources getResources() { return resources; }
}
