import { PNG } from 'pngjs';
import { PDFDocument } from 'pdf-lib';
import { VideoStream, VideoBufferType } from '@livekit/rtc-node';

/**
 * Keep the latest decoded RGBA frame from a remote video track.
 * @param {import('@livekit/rtc-node').Track} track
 * @returns {{ getLatest: () => { rgba: Uint8Array, width: number, height: number } | null, close: () => Promise<void> }}
 */
export function followVideoTrack(track) {
  const stream = new VideoStream(track);
  /** @type {{ rgba: Uint8Array, width: number, height: number } | null} */
  let latest = null;
  let closed = false;

  const reader = (async () => {
    for await (const event of stream) {
      if (closed) break;
      const frame = event.frame;
      if (!frame?.width || !frame?.height) continue;
      try {
        const converted =
          frame.type === VideoBufferType.RGBA ? frame : frame.convert(VideoBufferType.RGBA);
        latest = {
          rgba: new Uint8Array(converted.data),
          width: converted.width,
          height: converted.height,
        };
      } catch (error) {
        console.warn('[capture] frame convert failed', error);
      }
    }
  })();

  return {
    getLatest: () => latest,
    close: async () => {
      closed = true;
      stream.cancel?.();
      await reader.catch(() => {});
    },
  };
}

/** Crude non-black / variance score so we prefer real document frames. */
export function frameScore(rgba) {
  if (!rgba?.length) return 0;
  let sum = 0;
  let sumSq = 0;
  let n = 0;
  // Sample every 32nd pixel for speed.
  for (let i = 0; i + 2 < rgba.length; i += 32 * 4) {
    const y = 0.299 * rgba[i] + 0.587 * rgba[i + 1] + 0.114 * rgba[i + 2];
    sum += y;
    sumSq += y * y;
    n += 1;
  }
  if (!n) return 0;
  const mean = sum / n;
  const variance = Math.max(0, sumSq / n - mean * mean);
  // Penalize near-black frames.
  return variance * (0.25 + mean / 255);
}

/**
 * @param {Array<{ rgba: Uint8Array, width: number, height: number }>} frames
 * @returns {Promise<Uint8Array>}
 */
export async function framesToPdf(frames) {
  if (!frames.length) throw new Error('No frames to encode');
  const pdf = await PDFDocument.create();
  for (const frame of frames) {
    const png = rgbaToPng(frame.rgba, frame.width, frame.height);
    const embedded = await pdf.embedPng(png);
    const page = pdf.addPage([embedded.width, embedded.height]);
    page.drawImage(embedded, {
      x: 0,
      y: 0,
      width: embedded.width,
      height: embedded.height,
    });
  }
  return pdf.save();
}

function rgbaToPng(rgba, width, height) {
  const png = new PNG({ width, height });
  png.data = Buffer.from(rgba);
  return PNG.sync.write(png);
}

/**
 * Collect up to `count` strong frames over `durationMs`.
 * @param {() => ({ rgba: Uint8Array, width: number, height: number } | null)} getLatest
 * @param {{ durationMs?: number, count?: number, minScore?: number }} [options]
 */
export async function collectBestFrames(getLatest, options = {}) {
  const durationMs = options.durationMs ?? 8_000;
  const count = options.count ?? 2;
  const minScore = options.minScore ?? 80;
  const started = Date.now();
  /** @type {Array<{ frame: { rgba: Uint8Array, width: number, height: number }, score: number }>} */
  const best = [];

  while (Date.now() - started < durationMs) {
    const frame = getLatest();
    if (frame) {
      const score = frameScore(frame.rgba);
      if (score >= minScore) {
        best.push({ frame, score });
        best.sort((a, b) => b.score - a.score);
        if (best.length > count * 3) best.length = count * 3;
      }
    }
    await new Promise(r => setTimeout(r, 350));
  }

  const picked = [];
  for (const item of best) {
    if (picked.length >= count) break;
    // Deduplicate near-identical scores/time by keeping spaced picks.
    if (picked.some(p => Math.abs(p.score - item.score) < 1)) continue;
    picked.push(item);
  }
  if (!picked.length && best[0]) picked.push(best[0]);
  return picked.map(p => p.frame);
}
