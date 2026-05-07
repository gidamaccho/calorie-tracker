import { useState } from 'react';

type Props = {
  onAdd: (name: string, calories: number) => void;
};

export const MealForm = ({ onAdd }: Props) => {
  const [name, setName] = useState('');
  const [calories, setCalories] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const cal = parseInt(calories, 10);
    if (!name.trim() || isNaN(cal) || cal <= 0) return;
    onAdd(name.trim(), cal);
    setName('');
    setCalories('');
  };

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
      <h2 className="text-lg font-semibold text-gray-700 mb-4">食事を追加</h2>
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
