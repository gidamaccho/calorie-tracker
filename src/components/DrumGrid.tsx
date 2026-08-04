import type { Archetype } from '../data/techno';

const STEPS_PER_BAR = 16;

const ROWS = [
  { key: 'kick', label: 'Kick', symbol: '●', color: 'bg-gray-800' },
  { key: 'clap', label: 'Clap', symbol: '▲', color: 'bg-rose-500' },
  { key: 'hat', label: 'Hat', symbol: '×', color: 'bg-cyan-500' },
] as const;

type Props = {
  archetype: Archetype;
  currentStep: number;
};

/** ドラムは五線譜より読みやすい16分のステップグリッドで表示する */
export const DrumGrid = ({ archetype, currentStep }: Props) => {
  const cols = { gridTemplateColumns: `repeat(${STEPS_PER_BAR}, minmax(0, 1fr))` };

  return (
    <div className="flex flex-col gap-3">
      {Array.from({ length: archetype.bars }, (_, bar) => {
        const offset = bar * STEPS_PER_BAR;
        const localCurrent =
          currentStep >= offset && currentStep < offset + STEPS_PER_BAR ? currentStep - offset : -1;

        return (
          <div key={bar} className="flex items-center gap-2">
            <div className="w-9 shrink-0 text-[10px] text-gray-400 text-right leading-4">
              {ROWS.map(row => (
                <div key={row.key} className="h-5 flex items-center justify-end">
                  {row.label}
                </div>
              ))}
              <div className="h-4" />
            </div>
            <div className="flex-1 min-w-0">
              {ROWS.map(row => (
                <div key={row.key} className="grid gap-[2px] h-5 items-center" style={cols}>
                  {Array.from({ length: STEPS_PER_BAR }, (_, step) => {
                    const on = archetype[row.key].includes(offset + step);
                    const isCurrent = step === localCurrent;
                    return (
                      <div
                        key={step}
                        className={[
                          'h-4 rounded-[3px] flex items-center justify-center text-[9px] leading-none transition-colors',
                          on
                            ? `${row.color} text-white`
                            : step % 4 === 0
                              ? 'bg-gray-200 text-transparent'
                              : 'bg-gray-100 text-transparent',
                          isCurrent ? 'ring-2 ring-indigo-400' : '',
                        ].join(' ')}
                      >
                        {row.symbol}
                      </div>
                    );
                  })}
                </div>
              ))}
              <div className="grid gap-[2px] h-4 items-center text-[9px] text-gray-400" style={cols}>
                {Array.from({ length: STEPS_PER_BAR }, (_, step) => (
                  <div key={step} className="text-center">
                    {step % 4 === 0 ? step / 4 + 1 : ''}
                  </div>
                ))}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
};
