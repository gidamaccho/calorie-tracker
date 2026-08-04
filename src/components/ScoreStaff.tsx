import type { BassNote } from '../data/techno';

/**
 * ベースライン用の五線譜（ヘ音記号）。
 * 音符は16分グリッドの位置にそのまま配置する「グリッド譜」方式で、
 * 休符は書かずに空きで表現する。
 */

const LINE_GAP = 9;
const STAFF_H = LINE_GAP * 4;
const TOP_PAD = 40;
const BOT_PAD = 34;
const CLEF_W = 32;
const VB_W = 348;
const RIGHT_PAD = 8;
const STEPS_PER_BAR = 16;
const STEP_W = (VB_W - CLEF_W - RIGHT_PAD) / STEPS_PER_BAR;
const VB_H = TOP_PAD + STAFF_H + BOT_PAD;
const BOTTOM_LINE_Y = TOP_PAD + STAFF_H;
const MIDDLE_Y = TOP_PAD + STAFF_H / 2;
const STEM_LEN = 24;
const HEAD_RX = 4.8;
const HEAD_RY = 3.5;
const BEAM_H = 2.8;
const BEAM_GAP = 4.8;

/** ピッチクラス → [音名インデックス(0=C), 変化記号] */
const SHARP_SPELLING: readonly (readonly [number, number])[] = [
  [0, 0], [0, 1], [1, 0], [1, 1], [2, 0], [3, 0], [3, 1], [4, 0], [4, 1], [5, 0], [5, 1], [6, 0],
];
const FLAT_SPELLING: readonly (readonly [number, number])[] = [
  [0, 0], [1, -1], [1, 0], [2, -1], [2, 0], [3, 0], [4, -1], [4, 0], [5, -1], [5, 0], [6, -1], [6, 0],
];

/** ヘ音記号の五線の一番下の線は G2（MIDI 43）＝ダイアトニック番号18 */
const BOTTOM_LINE_DIATONIC = 18;

const staffY = (midi: number, accidentals: 'sharp' | 'flat') => {
  const table = accidentals === 'sharp' ? SHARP_SPELLING : FLAT_SPELLING;
  const [letter, alter] = table[((midi % 12) + 12) % 12];
  const octave = Math.floor(midi / 12) - 1;
  const diatonic = octave * 7 + letter;
  return {
    y: BOTTOM_LINE_Y - (diatonic - BOTTOM_LINE_DIATONIC) * (LINE_GAP / 2),
    alter,
  };
};

const noteX = (localStep: number) => CLEF_W + localStep * STEP_W + STEP_W / 2;

const ledgerYs = (y: number) => {
  const ys: number[] = [];
  for (let ly = TOP_PAD - LINE_GAP; ly >= y - 0.1; ly -= LINE_GAP) ys.push(ly);
  for (let ly = BOTTOM_LINE_Y + LINE_GAP; ly <= y + 0.1; ly += LINE_GAP) ys.push(ly);
  return ys;
};

type PlacedNote = {
  step: number;
  len: number;
  x: number;
  y: number;
  alter: number;
};

const BassClef = () => (
  <g transform={`translate(11, ${TOP_PAD + LINE_GAP})`} className="fill-gray-700">
    <circle cx="0" cy="0" r="2.7" />
    <path
      d="M 0,0 C 0,-5.5 6,-7 8.5,-3.5 C 11,0 7,7 0,11.5 C -2,13 -4,14 -5.5,14.5"
      fill="none"
      stroke="currentColor"
      className="stroke-gray-700"
      strokeWidth="3"
      strokeLinecap="round"
    />
    <circle cx="11.5" cy="-4.5" r="1.3" />
    <circle cx="11.5" cy="4.5" r="1.3" />
  </g>
);

type SystemProps = {
  bar: number;
  notes: BassNote[];
  root: number;
  accidentals: 'sharp' | 'flat';
  isLast: boolean;
  currentLocalStep: number | null;
};

const StaffSystem = ({ bar, notes, root, accidentals, isLast, currentLocalStep }: SystemProps) => {
  const placed: PlacedNote[] = notes.map(n => {
    const localStep = n.step % STEPS_PER_BAR;
    const { y, alter } = staffY(root + n.semi, accidentals);
    return { step: localStep, len: n.len, x: noteX(localStep), y, alter };
  });

  // 拍（16分×4）ごとに符尾をまとめて連桁にする
  const beats: PlacedNote[][] = [[], [], [], []];
  for (const note of placed) beats[Math.floor(note.step / 4)].push(note);

  return (
    <svg
      viewBox={`0 0 ${VB_W} ${VB_H}`}
      className="w-full h-auto"
      role="img"
      aria-label={`${bar + 1}小節目のベース譜`}
    >
      {/* 拍アタリ＆再生位置 */}
      {currentLocalStep !== null && (
        <rect
          x={CLEF_W + currentLocalStep * STEP_W}
          y={TOP_PAD - 22}
          width={STEP_W}
          height={STAFF_H + 44}
          className="fill-indigo-100"
        />
      )}
      {[0, 1, 2, 3].map(beat => (
        <line
          key={beat}
          x1={CLEF_W + beat * 4 * STEP_W}
          y1={TOP_PAD - 12}
          x2={CLEF_W + beat * 4 * STEP_W}
          y2={BOTTOM_LINE_Y + 12}
          className="stroke-gray-200"
          strokeWidth="1"
          strokeDasharray="2 3"
        />
      ))}

      {/* 五線 */}
      {[0, 1, 2, 3, 4].map(i => (
        <line
          key={i}
          x1={CLEF_W - 2}
          y1={TOP_PAD + i * LINE_GAP}
          x2={VB_W - RIGHT_PAD}
          y2={TOP_PAD + i * LINE_GAP}
          className="stroke-gray-400"
          strokeWidth="1"
        />
      ))}
      <line
        x1={CLEF_W - 2}
        y1={TOP_PAD}
        x2={CLEF_W - 2}
        y2={BOTTOM_LINE_Y}
        className="stroke-gray-500"
        strokeWidth="1.6"
      />
      <line
        x1={VB_W - RIGHT_PAD}
        y1={TOP_PAD}
        x2={VB_W - RIGHT_PAD}
        y2={BOTTOM_LINE_Y}
        className="stroke-gray-600"
        strokeWidth={isLast ? 3.6 : 1.6}
      />

      <BassClef />

      <text x={CLEF_W - 2} y={TOP_PAD - 14} className="fill-gray-400" fontSize="11">
        {bar + 1}
      </text>

      {beats.map((group, beat) => {
        if (group.length === 0) return null;
        const avgY = group.reduce((s, n) => s + n.y, 0) / group.length;
        const up = avgY >= MIDDLE_Y;
        const stemX = (n: PlacedNote) => (up ? n.x + HEAD_RX - 0.5 : n.x - HEAD_RX + 0.5);
        const beamY = up
          ? Math.min(...group.map(n => n.y - STEM_LEN))
          : Math.max(...group.map(n => n.y + STEM_LEN));
        const beamed = group.length > 1;

        return (
          <g key={beat} className="fill-gray-800 stroke-gray-800">
            {group.map(n => (
              <g key={n.step}>
                {ledgerYs(n.y).map(ly => (
                  <line
                    key={ly}
                    x1={n.x - 8}
                    y1={ly}
                    x2={n.x + 8}
                    y2={ly}
                    className="stroke-gray-400"
                    strokeWidth="1"
                  />
                ))}
                {n.alter !== 0 && (
                  <text
                    x={n.x - HEAD_RX - 2}
                    y={n.y + 3.5}
                    textAnchor="end"
                    fontSize="11"
                    className="fill-gray-700 stroke-none"
                  >
                    {n.alter > 0 ? '♯' : '♭'}
                  </text>
                )}
                <ellipse
                  cx={n.x}
                  cy={n.y}
                  rx={HEAD_RX}
                  ry={HEAD_RY}
                  transform={`rotate(-20 ${n.x} ${n.y})`}
                  className="stroke-none"
                />
                {n.len < 4 && (
                  <line
                    x1={stemX(n)}
                    y1={n.y}
                    x2={stemX(n)}
                    y2={beamY}
                    strokeWidth="1.5"
                  />
                )}
                {/* 単独の音符は連桁ではなく旗をつける */}
                {!beamed && n.len < 4 && (
                  <>
                    <path
                      d={`M ${stemX(n)},${beamY} c 5,${up ? 3 : -3} 7,${up ? 8 : -8} 3,${up ? 13 : -13}`}
                      fill="none"
                      strokeWidth="2.4"
                      strokeLinecap="round"
                    />
                    {n.len === 1 && (
                      <path
                        d={`M ${stemX(n)},${beamY + (up ? BEAM_GAP : -BEAM_GAP)} c 5,${up ? 3 : -3} 7,${up ? 8 : -8} 3,${up ? 13 : -13}`}
                        fill="none"
                        strokeWidth="2.4"
                        strokeLinecap="round"
                      />
                    )}
                  </>
                )}
              </g>
            ))}

            {beamed && (
              <>
                <rect
                  x={stemX(group[0])}
                  y={up ? beamY : beamY - BEAM_H}
                  width={stemX(group[group.length - 1]) - stemX(group[0])}
                  height={BEAM_H}
                  className="stroke-none"
                />
                {group.map((n, i) => {
                  if (n.len !== 1) return null;
                  const prev = group[i - 1];
                  const next = group[i + 1];
                  const y2 = up ? beamY + BEAM_GAP : beamY - BEAM_GAP - BEAM_H;
                  if (next && next.len === 1) {
                    return (
                      <rect
                        key={`s${n.step}`}
                        x={stemX(n)}
                        y={y2}
                        width={stemX(next) - stemX(n)}
                        height={BEAM_H}
                        className="stroke-none"
                      />
                    );
                  }
                  if (prev && prev.len === 1) return null;
                  // 前後に16分がない場合は短い副桁（フック）だけ描く
                  return (
                    <rect
                      key={`s${n.step}`}
                      x={prev ? stemX(n) - 7 : stemX(n)}
                      y={y2}
                      width={7}
                      height={BEAM_H}
                      className="stroke-none"
                    />
                  );
                })}
              </>
            )}
          </g>
        );
      })}
    </svg>
  );
};

type Props = {
  bass: BassNote[];
  bars: number;
  root: number;
  accidentals: 'sharp' | 'flat';
  currentStep: number;
};

export const ScoreStaff = ({ bass, bars, root, accidentals, currentStep }: Props) => (
  <div className="flex flex-col gap-1">
    {Array.from({ length: bars }, (_, bar) => (
      <StaffSystem
        key={bar}
        bar={bar}
        notes={bass.filter(n => Math.floor(n.step / STEPS_PER_BAR) === bar)}
        root={root}
        accidentals={accidentals}
        isLast={bar === bars - 1}
        currentLocalStep={
          Math.floor(currentStep / STEPS_PER_BAR) === bar ? currentStep % STEPS_PER_BAR : null
        }
      />
    ))}
  </div>
);
