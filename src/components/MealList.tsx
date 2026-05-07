import type { Meal } from '../types';

type Props = {
  meals: Meal[];
  onDelete: (id: string) => void;
};

const formatTime = (iso: string) =>
  new Date(iso).toLocaleTimeString('ja-JP', { hour: '2-digit', minute: '2-digit' });

export const MealList = ({ meals, onDelete }: Props) => {
  if (meals.length === 0) {
    return (
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6 text-center text-gray-400 text-sm">
        まだ食事が記録されていません
      </div>
    );
  }

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
      <h2 className="text-lg font-semibold text-gray-700 mb-4">今日の食事</h2>
      <ul className="flex flex-col gap-2">
        {meals.map(meal => (
          <li
            key={meal.id}
            className="flex items-center justify-between bg-gray-50 rounded-xl px-4 py-3"
          >
            <div className="flex flex-col">
              <span className="text-sm font-medium text-gray-800">{meal.name}</span>
              <span className="text-xs text-gray-400">{formatTime(meal.time)}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold text-green-600">{meal.calories.toLocaleString()} kcal</span>
              <button
                onClick={() => onDelete(meal.id)}
                className="flex items-center justify-center w-10 h-10 rounded-full text-gray-300 active:text-red-400 active:bg-red-50 transition-colors"
                aria-label="削除"
              >
                ✕
              </button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
};
