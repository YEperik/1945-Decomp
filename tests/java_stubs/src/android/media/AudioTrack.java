package android.media;
public class AudioTrack {
    public static final int STATE_INITIALIZED = 1, MODE_STREAM = 1, WRITE_BLOCKING = 0;
    public static final int PLAYSTATE_PLAYING = 3;
    public static final int ERROR_INVALID_OPERATION = -3, ERROR_BAD_VALUE = -2;
    public static int getMinBufferSize(int sampleRate, int channelConfig, int audioFormat) { return 2048; }
    public static class Builder {
        public Builder setAudioAttributes(AudioAttributes attributes) { return this; }
        public Builder setAudioFormat(AudioFormat format) { return this; }
        public Builder setTransferMode(int mode) { return this; }
        public Builder setBufferSizeInBytes(int size) { return this; }
        public AudioTrack build() { return new AudioTrack(); }
    }
    public int getState() { return STATE_INITIALIZED; }
    public int getPlayState() { return PLAYSTATE_PLAYING; }
    public void play() { }
    public int write(short[] data, int offset, int size, int mode) { return size; }
    public void pause() { }
    public void flush() { }
    public void stop() { }
    public void release() { }
}
