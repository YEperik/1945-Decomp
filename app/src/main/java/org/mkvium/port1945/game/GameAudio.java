package org.mkvium.port1945.game;

import android.media.AudioAttributes;
import android.media.AudioFormat;
import android.media.AudioTrack;
import android.os.Process;
import android.util.Log;

/** Dedicated AudioTrack worker for procedural prototype SFX; no original music is included. */
public final class GameAudio {
    private static final int SAMPLE_RATE = 22050;
    private static final int CHUNK_SAMPLES = 512;

    private volatile boolean running;
    private volatile AudioTrack activeTrack;
    private Thread worker;

    public synchronized void start() {
        if (running) {
            return;
        }
        running = true;
        worker = new Thread(this::runAudio, "1945-audio");
        worker.setDaemon(true);
        worker.start();
    }

    public synchronized void stop() {
        Thread threadToJoin = worker;
        AudioTrack track = activeTrack;
        running = false;
        if (track != null) {
            /* Try every stop operation independently: one terminal-state exception must not
               prevent stop(), which is the call most likely to unblock a blocking write. */
            try {
                track.pause();
            } catch (IllegalStateException exception) {
                Log.w("1945Audio", "AudioTrack pause was already in a terminal state", exception);
            }
            try {
                track.flush();
            } catch (IllegalStateException exception) {
                Log.w("1945Audio", "AudioTrack flush was already in a terminal state", exception);
            }
            try {
                track.stop();
            } catch (IllegalStateException exception) {
                Log.w("1945Audio", "AudioTrack stop was already in a terminal state", exception);
            }
        }
        if (threadToJoin != null && threadToJoin != Thread.currentThread()) {
            boolean interrupted = false;
            while (threadToJoin.isAlive()) {
                try {
                    threadToJoin.join(250L);
                } catch (InterruptedException exception) {
                    interrupted = true;
                }
            }
            if (interrupted) {
                Thread.currentThread().interrupt();
            }
        }
        if (worker == threadToJoin) {
            worker = null;
        }
    }

    private void runAudio() {
        AudioTrack track = null;
        try {
            Process.setThreadPriority(Process.THREAD_PRIORITY_AUDIO);
            GameBridge.nativeInitAudio();
            int minimumBytes = AudioTrack.getMinBufferSize(
                SAMPLE_RATE, AudioFormat.CHANNEL_OUT_MONO, AudioFormat.ENCODING_PCM_16BIT);
            if (minimumBytes <= 0) {
                Log.e("1945Audio", "AudioTrack reported an invalid minimum buffer size: " + minimumBytes);
                return;
            }
            int bufferBytes = Math.max(minimumBytes, CHUNK_SAMPLES * 4);
            AudioFormat format = new AudioFormat.Builder()
                .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                .setSampleRate(SAMPLE_RATE)
                .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                .build();
            AudioAttributes attributes = new AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_GAME)
                .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                .build();
            track = new AudioTrack.Builder()
                .setAudioAttributes(attributes)
                .setAudioFormat(format)
                .setTransferMode(AudioTrack.MODE_STREAM)
                .setBufferSizeInBytes(bufferBytes)
                .build();
            if (track.getState() != AudioTrack.STATE_INITIALIZED || !running) {
                return;
            }
            activeTrack = track;
            track.play();
            short[] samples = new short[CHUNK_SAMPLES];
            while (running) {
                GameBridge.nativeMixAudio(samples);
                int offset = 0;
                while (running && offset < samples.length) {
                    int written = track.write(samples, offset, samples.length - offset,
                                              AudioTrack.WRITE_BLOCKING);
                    if (written <= 0) {
                        if (written < 0) {
                            Log.e("1945Audio", "AudioTrack.write failed with code " + written);
                        } else {
                            Log.e("1945Audio", "AudioTrack.write made no progress; stopping audio worker");
                        }
                        running = false;
                        break;
                    }
                    offset += written;
                }
            }
        } catch (RuntimeException exception) {
            // Audio is optional for startup; retain an actionable diagnostic if the platform rejects it.
            Log.e("1945Audio", "Procedural SFX stream stopped; gameplay continues without audio", exception);
        } finally {
            activeTrack = null;
            if (track != null) {
                try {
                    if (track.getPlayState() == AudioTrack.PLAYSTATE_PLAYING) {
                        track.pause();
                    }
                } catch (IllegalStateException exception) {
                    Log.w("1945Audio", "AudioTrack pause cleanup encountered a terminal state", exception);
                }
                try {
                    track.flush();
                } catch (IllegalStateException exception) {
                    Log.w("1945Audio", "AudioTrack flush cleanup encountered a terminal state", exception);
                }
                try {
                    track.release();
                } catch (RuntimeException exception) {
                    Log.e("1945Audio", "AudioTrack release failed", exception);
                }
            }
            running = false;
        }
    }
}
