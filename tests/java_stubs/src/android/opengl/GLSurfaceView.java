package android.opengl;
import android.content.Context;
import android.view.View;
import javax.microedition.khronos.egl.EGLConfig;
import javax.microedition.khronos.opengles.GL10;
public class GLSurfaceView extends View {
    public static final int RENDERMODE_CONTINUOUSLY = 1;
    public interface Renderer {
        void onSurfaceCreated(GL10 unused, EGLConfig config);
        void onSurfaceChanged(GL10 unused, int width, int height);
        void onDrawFrame(GL10 unused);
    }
    public GLSurfaceView(Context context) { super(context); }
    public void setEGLContextClientVersion(int version) { }
    public void setPreserveEGLContextOnPause(boolean preserve) { }
    public void setRenderer(Renderer renderer) { }
    public void setRenderMode(int mode) { }
    public void onResume() { }
    public void onPause() { }
}
