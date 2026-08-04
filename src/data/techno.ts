/**
 * 最新テクノの人気曲リストと、楽譜表示に使うパターン定義。
 *
 * 【重要】ここに入っている譜例は原曲の採譜ではありません。
 * 各曲が属するサブジャンルで定番となっているリズム／ベースの型を、
 * 学習用に書き起こしたオリジナルの譜例です（キーとテンポも譜例側の設定）。
 */

export type SubgenreId = 'melodic' | 'peaktime' | 'hard' | 'industrial';

/** ベース音符。step は16分グリッドの位置、len は16分いくつ分、semi はルートからの半音差 */
export type BassNote = {
  step: number;
  len: number;
  semi: number;
};

export type Archetype = {
  id: SubgenreId;
  label: string;
  description: string;
  bars: number;
  kick: number[];
  clap: number[];
  hat: number[];
  bass: BassNote[];
};

export type TechnoTrack = {
  id: string;
  title: string;
  artists: string;
  subgenre: SubgenreId;
  /** チャート／メディアでの出典 */
  source: string;
  sourceUrl: string;
  /** 以下は譜例の設定であって、原曲の実測値ではない */
  bpm: number;
  keyLabel: string;
  /** 譜例のベースのルート音（MIDIノート番号） */
  root: number;
  accidentals: 'sharp' | 'flat';
};

export const SUBGENRE_LABEL: Record<SubgenreId, string> = {
  melodic: 'Melodic House & Techno',
  peaktime: 'Peak Time / Driving',
  hard: 'Hard Techno',
  industrial: 'Industrial / Acid',
};

export const SUBGENRE_COLOR: Record<SubgenreId, string> = {
  melodic: 'bg-indigo-50 text-indigo-600 border-indigo-100',
  peaktime: 'bg-cyan-50 text-cyan-700 border-cyan-100',
  hard: 'bg-rose-50 text-rose-600 border-rose-100',
  industrial: 'bg-amber-50 text-amber-700 border-amber-100',
};

const range16 = (bar: number) => [0, 4, 8, 12].map(s => s + bar * 16);

export const ARCHETYPES: Record<SubgenreId, Archetype> = {
  melodic: {
    id: 'melodic',
    label: 'オフビート・ベース型',
    description:
      '4つ打ちキックの裏に8分のベースを置く、メロディック・テクノの基本形。2小節目で3度・5度に動かして展開を作る。',
    bars: 2,
    kick: [...range16(0), ...range16(1)],
    clap: [4, 12, 20, 28],
    hat: [2, 6, 10, 14, 18, 22, 26, 30],
    bass: [
      { step: 0, len: 2, semi: 0 },
      { step: 3, len: 1, semi: 0 },
      { step: 6, len: 2, semi: 3 },
      { step: 10, len: 2, semi: 0 },
      { step: 14, len: 2, semi: -2 },
      { step: 16, len: 2, semi: 0 },
      { step: 19, len: 1, semi: 0 },
      { step: 22, len: 2, semi: 3 },
      { step: 26, len: 2, semi: 7 },
      { step: 30, len: 2, semi: 5 },
    ],
  },
  peaktime: {
    id: 'peaktime',
    label: 'ローリング16分ベース型',
    description:
      'キックの隙間を16分のルート音で埋め続ける、ピークタイム定番の推進力パターン。最後の1拍だけ音程を上げて次の小節へ繋ぐ。',
    bars: 2,
    kick: [...range16(0), ...range16(1)],
    clap: [4, 12, 20, 28],
    hat: [2, 6, 10, 14, 18, 22, 26, 30],
    bass: [
      ...[1, 2, 3, 5, 6, 7, 9, 10, 11, 13, 14, 15].map(step => ({ step, len: 1, semi: 0 })),
      ...[17, 18, 19, 21, 22, 23, 25, 26, 27].map(step => ({ step, len: 1, semi: 0 })),
      { step: 29, len: 1, semi: 0 },
      { step: 30, len: 1, semi: 3 },
      { step: 31, len: 1, semi: 5 },
    ],
  },
  hard: {
    id: 'hard',
    label: 'オフビート＋オクターブ型',
    description:
      '8分裏のみを鳴らす骨太なベースに、2小節目でオクターブ上を混ぜる型。ハードテクノ／ハードグルーヴの常套句。',
    bars: 2,
    kick: [...range16(0), ...range16(1)],
    clap: [4, 12, 20, 28],
    hat: [2, 6, 10, 14, 18, 22, 26, 29, 30, 31],
    bass: [
      { step: 2, len: 2, semi: 0 },
      { step: 6, len: 2, semi: 0 },
      { step: 10, len: 2, semi: 0 },
      { step: 14, len: 2, semi: 0 },
      { step: 18, len: 2, semi: 0 },
      { step: 22, len: 2, semi: 0 },
      { step: 26, len: 2, semi: 12 },
      { step: 30, len: 2, semi: 10 },
    ],
  },
  industrial: {
    id: 'industrial',
    label: 'アシッド・16分ライン型',
    description:
      '16分をオクターブと短3度で飛ばすアシッド系ライン。インダストリアル寄りのセットで多用される動きの型。',
    bars: 2,
    kick: [...range16(0), ...range16(1)],
    clap: [8, 24],
    hat: [1, 2, 5, 6, 9, 10, 13, 14, 17, 18, 21, 22, 25, 26, 29, 30],
    bass: [
      { step: 0, len: 1, semi: 0 },
      { step: 2, len: 1, semi: 0 },
      { step: 3, len: 1, semi: 12 },
      { step: 5, len: 1, semi: 0 },
      { step: 6, len: 1, semi: 10 },
      { step: 8, len: 1, semi: 0 },
      { step: 10, len: 1, semi: 3 },
      { step: 11, len: 1, semi: 12 },
      { step: 13, len: 1, semi: 0 },
      { step: 14, len: 1, semi: 10 },
      { step: 15, len: 1, semi: 12 },
      { step: 16, len: 1, semi: 0 },
      { step: 18, len: 1, semi: 0 },
      { step: 19, len: 1, semi: 12 },
      { step: 21, len: 1, semi: 0 },
      { step: 22, len: 1, semi: 10 },
      { step: 24, len: 1, semi: 0 },
      { step: 26, len: 1, semi: 5 },
      { step: 27, len: 1, semi: 3 },
      { step: 29, len: 1, semi: 0 },
      { step: 30, len: 1, semi: 0 },
      { step: 31, len: 1, semi: 12 },
    ],
  },
};

const BEATPORT_MELODIC = {
  source: 'Beatport Melodic House & Techno Top 10（2026年5月4日付）',
  sourceUrl: 'https://beachgrooves.com/chart/beatport-top-10-melodic-house-techno-04-may-2026/',
};

export const TECHNO_TRACKS: TechnoTrack[] = [
  {
    id: 'be-the-one',
    title: 'Be The One',
    artists: 'Adam Port, Keinemusik, SG Lewis',
    subgenre: 'melodic',
    ...BEATPORT_MELODIC,
    bpm: 124,
    keyLabel: 'A minor',
    root: 45,
    accidentals: 'sharp',
  },
  {
    id: 'recall',
    title: 'Recall',
    artists: 'HotLap',
    subgenre: 'melodic',
    ...BEATPORT_MELODIC,
    bpm: 122,
    keyLabel: 'D minor',
    root: 50,
    accidentals: 'flat',
  },
  {
    id: 'lazer-beams',
    title: 'Lazer Beams',
    artists: 'Green Velvet, Harvard Bass',
    subgenre: 'peaktime',
    ...BEATPORT_MELODIC,
    bpm: 132,
    keyLabel: 'E minor',
    root: 40,
    accidentals: 'sharp',
  },
  {
    id: 'like-a-child',
    title: 'Like A Child',
    artists: 'Armin van Buuren, Argy, Marlo Rex',
    subgenre: 'melodic',
    ...BEATPORT_MELODIC,
    bpm: 126,
    keyLabel: 'G minor',
    root: 43,
    accidentals: 'flat',
  },
  {
    id: 'spotlight',
    title: 'Spotlight',
    artists: 'Andrea Oliva',
    subgenre: 'melodic',
    ...BEATPORT_MELODIC,
    bpm: 125,
    keyLabel: 'A minor',
    root: 45,
    accidentals: 'sharp',
  },
  {
    id: 'turn-up-the-dose',
    title: 'Turn Up The Dose',
    artists: 'KREAM, SCRIPT',
    subgenre: 'peaktime',
    ...BEATPORT_MELODIC,
    bpm: 130,
    keyLabel: 'F minor',
    root: 41,
    accidentals: 'flat',
  },
  {
    id: 'one-mind',
    title: 'One Mind',
    artists: 'Charlotte de Witte, Sara Landry',
    subgenre: 'hard',
    source: 'DJane Mag「Sónar 2026」特集（2026年）で紹介された共作',
    sourceUrl:
      'https://djanemag.com/news/charlotte-de-witte-amelie-lens-and-sara-landry-lead-technos-new-era-sonar-2026',
    bpm: 150,
    keyLabel: 'A minor',
    root: 45,
    accidentals: 'sharp',
  },
  {
    id: 'thistle',
    title: 'Thistle',
    artists: 'Skrillex, Randomer, Blawan, MC Dricka',
    subgenre: 'industrial',
    source: 'Mixmag「The Best Tracks Of The Year 2026 So Far」トップ掲載',
    sourceUrl: 'https://mixmag.net/feature/best-dance-electronic-club-tracks-2026',
    bpm: 145,
    keyLabel: 'D minor',
    root: 38,
    accidentals: 'flat',
  },
];
