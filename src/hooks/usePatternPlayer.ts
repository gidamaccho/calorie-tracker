import { useCallback, useEffect, useRef, useState } from 'react';
import type { Archetype } from '../data/techno';

/**
 * 譜例をそのまま Web Audio で鳴らすための簡易シーケンサ。
 * 外部ライブラリなしで、キック／クラップ／ハット／ベースを合成する。
 */

const LOOKAHEAD_MS = 25;
const SCHEDULE_AHEAD_SEC = 0.12;
const STEPS_PER_BAR = 16;

const midiToFreq = (midi: number) => 440 * 2 ** ((midi - 69) / 12);

const createNoiseBuffer = (ctx: AudioContext) => {
  const buffer = ctx.createBuffer(1, Math.floor(ctx.sampleRate * 0.4), ctx.sampleRate);
  const data = buffer.getChannelData(0);
  for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1;
  return buffer;
};

const playKick = (ctx: AudioContext, dest: AudioNode, t: number) => {
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.type = 'sine';
  osc.frequency.setValueAtTime(150, t);
  osc.frequency.exponentialRampToValueAtTime(45, t + 0.11);
  gain.gain.setValueAtTime(1, t);
  gain.gain.exponentialRampToValueAtTime(0.001, t + 0.32);
  osc.connect(gain).connect(dest);
  osc.start(t);
  osc.stop(t + 0.35);
};

const playNoise = (
  ctx: AudioContext,
  dest: AudioNode,
  buffer: AudioBuffer,
  t: number,
  opts: { type: BiquadFilterType; freq: number; level: number; decay: number },
) => {
  const src = ctx.createBufferSource();
  const filter = ctx.createBiquadFilter();
  const gain = ctx.createGain();
  src.buffer = buffer;
  filter.type = opts.type;
  filter.frequency.value = opts.freq;
  gain.gain.setValueAtTime(opts.level, t);
  gain.gain.exponentialRampToValueAtTime(0.001, t + opts.decay);
  src.connect(filter).connect(gain).connect(dest);
  src.start(t);
  src.stop(t + opts.decay + 0.02);
};

const playBass = (ctx: AudioContext, dest: AudioNode, t: number, midi: number, dur: number) => {
  const osc = ctx.createOscillator();
  const filter = ctx.createBiquadFilter();
  const gain = ctx.createGain();
  osc.type = 'sawtooth';
  osc.frequency.value = midiToFreq(midi);
  filter.type = 'lowpass';
  filter.Q.value = 6;
  filter.frequency.setValueAtTime(1400, t);
  filter.frequency.exponentialRampToValueAtTime(320, t + Math.min(dur, 0.25));
  gain.gain.setValueAtTime(0.0001, t);
  gain.gain.exponentialRampToValueAtTime(0.5, t + 0.008);
  gain.gain.exponentialRampToValueAtTime(0.001, t + dur);
  osc.connect(filter).connect(gain).connect(dest);
  osc.start(t);
  osc.stop(t + dur + 0.02);
};

type Pattern = {
  archetype: Archetype;
  bpm: number;
  root: number;
};

export const usePatternPlayer = ({ archetype, bpm, root }: Pattern) => {
  const [playing, setPlaying] = useState(false);
  const [step, setStep] = useState(-1);

  const ctxRef = useRef<AudioContext | null>(null);
  const noiseRef = useRef<AudioBuffer | null>(null);
  const masterRef = useRef<GainNode | null>(null);
  const timerRef = useRef<number | null>(null);
  const stepRef = useRef(0);
  const nextTimeRef = useRef(0);
  const genRef = useRef(0);

  const stop = useCallback(() => {
    genRef.current += 1;
    if (timerRef.current !== null) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    setPlaying(false);
    setStep(-1);
  }, []);

  const start = useCallback(() => {
    if (ctxRef.current === null) {
      const ctx = new AudioContext();
      const master = ctx.createGain();
      master.gain.value = 0.55;
      master.connect(ctx.destination);
      ctxRef.current = ctx;
      masterRef.current = master;
      noiseRef.current = createNoiseBuffer(ctx);
    }
    const ctx = ctxRef.current;
    const master = masterRef.current;
    const noise = noiseRef.current;
    if (!master || !noise) return;
    void ctx.resume();

    const gen = ++genRef.current;
    stepRef.current = 0;
    nextTimeRef.current = ctx.currentTime + 0.08;
    setPlaying(true);

    const schedule = () => {
      const stepDur = 60 / bpm / 4;
      const totalSteps = archetype.bars * STEPS_PER_BAR;

      while (nextTimeRef.current < ctx.currentTime + SCHEDULE_AHEAD_SEC) {
        const s = stepRef.current % totalSteps;
        const t = nextTimeRef.current;

        if (archetype.kick.includes(s)) playKick(ctx, master, t);
        if (archetype.clap.includes(s)) {
          playNoise(ctx, master, noise, t, { type: 'bandpass', freq: 1400, level: 0.5, decay: 0.16 });
        }
        if (archetype.hat.includes(s)) {
          playNoise(ctx, master, noise, t, { type: 'highpass', freq: 7500, level: 0.22, decay: 0.045 });
        }
        const bassNote = archetype.bass.find(n => n.step === s);
        if (bassNote) playBass(ctx, master, t, root + bassNote.semi, bassNote.len * stepDur * 0.9);

        const delayMs = Math.max(0, (t - ctx.currentTime) * 1000);
        window.setTimeout(() => {
          if (genRef.current === gen) setStep(s);
        }, delayMs);

        nextTimeRef.current += stepDur;
        stepRef.current = (s + 1) % totalSteps;
      }
    };

    schedule();
    timerRef.current = window.setInterval(schedule, LOOKAHEAD_MS);
  }, [archetype, bpm, root]);

  const toggle = useCallback(() => {
    if (timerRef.current !== null) stop();
    else start();
  }, [start, stop]);

  useEffect(
    () => () => {
      if (timerRef.current !== null) clearInterval(timerRef.current);
      void ctxRef.current?.close();
    },
    [],
  );

  return { playing, step, toggle };
};
