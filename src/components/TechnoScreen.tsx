import { useState } from 'react';
import {
  ARCHETYPES,
  SUBGENRE_COLOR,
  SUBGENRE_LABEL,
  TECHNO_TRACKS,
  type TechnoTrack,
} from '../data/techno';
import { usePatternPlayer } from '../hooks/usePatternPlayer';
import { ScoreStaff } from './ScoreStaff';
import { DrumGrid } from './DrumGrid';

const TrackScore = ({ track }: { track: TechnoTrack }) => {
  const archetype = ARCHETYPES[track.subgenre];
  const { playing, step, toggle } = usePatternPlayer({
    archetype,
    bpm: track.bpm,
    root: track.root,
  });

  return (
    <div className="mt-3 border-t border-gray-100 pt-3 flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-gray-500">
        <span className="bg-gray-100 rounded-md px-2 py-1">♩= {track.bpm}</span>
        <span className="bg-gray-100 rounded-md px-2 py-1">Key: {track.keyLabel}</span>
        <span className="bg-gray-100 rounded-md px-2 py-1">4/4・{archetype.bars}小節</span>
        <span className="bg-gray-100 rounded-md px-2 py-1">{archetype.label}</span>
      </div>

      <p className="text-xs text-gray-500 leading-relaxed">{archetype.description}</p>

      <button
        onClick={toggle}
        className={[
          'self-start flex items-center gap-2 rounded-xl px-4 py-3 text-sm font-medium text-white transition-colors min-h-[44px]',
          playing ? 'bg-gray-700 active:bg-gray-800' : 'bg-indigo-500 active:bg-indigo-600',
        ].join(' ')}
      >
        {playing ? '■ 停止' : '▶ 譜例を再生'}
      </button>

      <div>
        <h4 className="text-xs font-semibold text-gray-500 mb-1">ベース（ヘ音記号）</h4>
        <ScoreStaff
          bass={archetype.bass}
          bars={archetype.bars}
          root={track.root}
          accidentals={track.accidentals}
          currentStep={step}
        />
      </div>

      <div>
        <h4 className="text-xs font-semibold text-gray-500 mb-2">ドラム（16分ステップ）</h4>
        <DrumGrid archetype={archetype} currentStep={step} />
      </div>

      <p className="text-[11px] text-gray-400 leading-relaxed">
        出典: {track.source}
        <br />
        <a
          href={track.sourceUrl}
          target="_blank"
          rel="noreferrer noopener"
          className="text-indigo-500 underline break-all"
        >
          {track.sourceUrl}
        </a>
      </p>
    </div>
  );
};

export const TechnoScreen = () => {
  const [selectedId, setSelectedId] = useState(TECHNO_TRACKS[0].id);

  return (
    <div className="flex flex-col gap-4">
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
        <h2 className="text-lg font-semibold text-gray-700">最新テクノの人気曲</h2>
        <p className="text-xs text-gray-500 mt-2 leading-relaxed">
          2026年のチャート／メディア掲載から選んだテクノ系の話題曲です。曲名をタップすると譜例が開きます。
        </p>
        <p className="text-[11px] text-amber-700 bg-amber-50 border border-amber-100 rounded-xl px-3 py-2 mt-3 leading-relaxed">
          ※ 表示する譜例は<strong>原曲の採譜ではありません</strong>
          。著作権に配慮し、その曲が属するサブジャンルで定番のリズム／ベースの型を、学習用に書き起こしたオリジナルの譜例を表示しています（キー・テンポも譜例側の設定です）。
        </p>
      </div>

      <ul className="flex flex-col gap-3">
        {TECHNO_TRACKS.map((track, i) => {
          const selected = track.id === selectedId;
          return (
            <li
              key={track.id}
              className={[
                'bg-white rounded-2xl shadow-sm border p-4 transition-colors',
                selected ? 'border-indigo-200' : 'border-gray-100',
              ].join(' ')}
            >
              <button
                onClick={() => setSelectedId(selected ? '' : track.id)}
                className="w-full text-left flex items-start gap-3"
                aria-expanded={selected}
              >
                <span className="w-7 h-7 shrink-0 rounded-full bg-gray-100 text-gray-500 text-xs font-semibold flex items-center justify-center mt-0.5">
                  {i + 1}
                </span>
                <span className="flex-1 min-w-0">
                  <span className="block text-sm font-semibold text-gray-800">{track.title}</span>
                  <span className="block text-xs text-gray-500 mt-0.5">{track.artists}</span>
                  <span
                    className={`inline-block mt-2 text-[10px] border rounded-md px-2 py-0.5 ${SUBGENRE_COLOR[track.subgenre]}`}
                  >
                    {SUBGENRE_LABEL[track.subgenre]}
                  </span>
                </span>
                <span className="text-gray-300 text-xs mt-1">{selected ? '▲' : '▼'}</span>
              </button>

              {selected && <TrackScore key={track.id} track={track} />}
            </li>
          );
        })}
      </ul>
    </div>
  );
};
