import { AudioFrame, AudioSource, LocalAudioTrack, TrackSource } from '@livekit/rtc-node';

const SAMPLE_RATE = 48000;
const CHANNELS = 1;
const FRAME_MS = 20;
const SAMPLES = (SAMPLE_RATE * FRAME_MS) / 1000;

/**
 * Publish one unmuted microphone track (silence by default) so Chert accepts the agent.
 * Can temporarily play PCM16 mono@48k speech through the same track.
 * @param {import('@livekit/rtc-node').LocalParticipant} localParticipant
 */
export async function publishSilentMic(localParticipant) {
  const source = new AudioSource(SAMPLE_RATE, CHANNELS);
  const track = LocalAudioTrack.createAudioTrack('agent-mic', source);
  const silence = new Int16Array(SAMPLES * CHANNELS);
  /** @type {Int16Array | null} */
  let speech = null;
  let speechOffset = 0;
  /** @type {((value?: unknown) => void) | null} */
  let speechDone = null;

  const publish = await localParticipant.publishTrack(track, {
    source: TrackSource.SOURCE_MICROPHONE,
  });

  const timer = setInterval(() => {
    try {
      if (speech && speechOffset < speech.length) {
        const frame = new Int16Array(SAMPLES * CHANNELS);
        const remaining = speech.length - speechOffset;
        const copy = Math.min(frame.length, remaining);
        frame.set(speech.subarray(speechOffset, speechOffset + copy));
        speechOffset += copy;
        source.captureFrame(new AudioFrame(frame, SAMPLE_RATE, CHANNELS, SAMPLES));
        if (speechOffset >= speech.length) {
          speech = null;
          speechOffset = 0;
          const done = speechDone;
          speechDone = null;
          done?.();
        }
        return;
      }
      source.captureFrame(new AudioFrame(silence, SAMPLE_RATE, CHANNELS, SAMPLES));
    } catch {
      /* source closed */
    }
  }, FRAME_MS);

  return {
    track,
    source,
    publication: publish,
    sampleRate: SAMPLE_RATE,
    channels: CHANNELS,
    /**
     * Play mono PCM16 little-endian samples at 48kHz on the mic track.
     * @param {Int16Array} pcm
     */
    playPcm16(pcm) {
      return new Promise(resolve => {
        speech = pcm;
        speechOffset = 0;
        speechDone = resolve;
      });
    },
    stop: async () => {
      clearInterval(timer);
      speech = null;
      speechDone?.();
      speechDone = null;
      try { await track.close(); } catch { /* ignore */ }
      try { await source.close(); } catch { /* ignore */ }
    },
  };
}
