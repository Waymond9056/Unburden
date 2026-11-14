import { execFile } from 'node:child_process';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);

/**
 * Synthesize speech with macOS `say` as PCM16 mono @ 48kHz.
 * @param {string} text
 * @returns {Promise<Int16Array>}
 */
export async function synthesizeSpeechPcm16(text) {
  const dir = await mkdtemp(join(tmpdir(), 'unburden-say-'));
  const aiff = join(dir, 'speech.aiff');
  const wav = join(dir, 'speech.wav');
  try {
    await execFileAsync('say', ['-o', aiff, text], { timeout: 30_000 });
    await execFileAsync(
      'afconvert',
      ['-f', 'WAVE', '-d', 'LEI16@48000', '-c', '1', aiff, wav],
      { timeout: 30_000 },
    );
    const bytes = await readFile(wav);
    return wavToPcm16(bytes);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

function wavToPcm16(buf) {
  // Minimal WAV parse: find 'data' chunk.
  let offset = 12;
  while (offset + 8 <= buf.length) {
    const id = buf.toString('ascii', offset, offset + 4);
    const size = buf.readUInt32LE(offset + 4);
    const start = offset + 8;
    if (id === 'data') {
      const sampleBytes = buf.subarray(start, start + size);
      return new Int16Array(
        sampleBytes.buffer,
        sampleBytes.byteOffset,
        Math.floor(sampleBytes.byteLength / 2),
      );
    }
    offset = start + size + (size % 2);
  }
  throw new Error('WAV data chunk not found from afconvert output');
}
