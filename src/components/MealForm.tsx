import { useRef, useState } from 'react';
import { useMealPhoto } from '../hooks/useMealPhoto';

type Props = {
  onAdd: (name: string, calories: number) => void;
  /** 未設定なら写真からの入力は使えない。 */
  claudeApiKey: string;
};

export const MealForm = ({ onAdd, claudeApiKey }: Props) => {
  const [name, setName] = useState('');
  const [calories, setCalories] = useState('');
  const fileInput = useRef<HTMLInputElement>(null);
  const photo = useMealPhoto(claudeApiKey);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const cal = parseInt(calories, 10);
    if (!name.trim() || isNaN(cal) || cal <= 0) return;
    onAdd(name.trim(), cal);
    setName('');
    setCalories('');
    photo.reset();
  };

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    // 同じ写真を選び直せるように値をクリアしておく。
    e.target.value = '';
    if (!file) return;

    const result = await photo.analyze(file);
    if (result) {
      setName(result.name);
      setCalories(String(result.calories));
    }
  };

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
      <h2 className="text-lg font-semibold text-gray-700 mb-4">食事を追加</h2>

      {claudeApiKey && (
        <div className="mb-3">
          <input
            ref={fileInput}
            type="file"
            accept="image/*"
            capture="environment"
            onChange={handleFile}
            className="hidden"
          />
          <button
            type="button"
            onClick={() => fileInput.current?.click()}
            disabled={photo.analyzing}
            className="w-full flex items-center justify-center gap-2 border-2 border-dashed border-gray-200 text-gray-500 rounded-xl py-4 text-base active:bg-gray-50 disabled:opacity-60 transition-colors min-h-[52px]"
          >
            {photo.analyzing ? '写真を解析中…' : '📷 写真から入力'}
          </button>

          {photo.previewUrl && (
            <div className="mt-3 flex items-start gap-3">
              <img
                src={photo.previewUrl}
                alt="選んだ食事の写真"
                className="w-16 h-16 object-cover rounded-xl border border-gray-100 shrink-0"
              />
              <p className="text-xs text-gray-500 leading-relaxed">
                {photo.reading
                  ? `${photo.reading.items.join('、')}${photo.reading.note ? ` — ${photo.reading.note}` : ''}`
                  : photo.analyzing
                    ? '解析しています…'
                    : '解析できませんでした'}
              </p>
            </div>
          )}

          {photo.error && (
            <p className="mt-3 bg-amber-50 border border-amber-100 text-amber-700 rounded-xl px-4 py-3 text-sm">
              {photo.error}
            </p>
          )}
        </div>
      )}

      <form onSubmit={handleSubmit} className="flex flex-col gap-3">
        <input
          type="text"
          placeholder="食品名（例: ご飯 茶碗1杯）"
          value={name}
          onChange={e => setName(e.target.value)}
          enterKeyHint="next"
          className="border border-gray-200 rounded-xl px-4 py-3 text-base outline-none focus:ring-2 focus:ring-green-400 focus:border-transparent transition"
        />
        <input
          type="number"
          inputMode="numeric"
          placeholder="カロリー (kcal)"
          value={calories}
          onChange={e => setCalories(e.target.value)}
          min="1"
          enterKeyHint="done"
          className="border border-gray-200 rounded-xl px-4 py-3 text-base outline-none focus:ring-2 focus:ring-green-400 focus:border-transparent transition"
        />
        <button
          type="submit"
          className="bg-green-500 hover:bg-green-600 active:bg-green-700 text-white font-medium py-4 rounded-xl transition-colors text-base min-h-[52px]"
        >
          追加する
        </button>
      </form>
    </div>
  );
};
