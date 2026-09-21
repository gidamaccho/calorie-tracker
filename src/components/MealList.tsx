import type { Meal } from '../types';
import { MEAL_CATEGORIES } from '../lib/mealCategory';

type Props = {
  meals: Meal[];
  onDelete: (id: string) => void;
  /** Jev が判定中の食事ID。 */
  classifyingIds?: string[];
};

const formatTime = (iso: string) =>
  new Date(iso).toLocaleTimeString('ja-JP', { hour: '2-digit', minute: '2-digit' });

export const MealList = ({ meals, onDelete, classifyingIds = [] }: Props) => {
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
              <span className="flex items-center gap-2 text-xs text-gray-400">
                {formatTime(meal.time)}
                {meal.category ? (
                  <span
                    className="bg-white border border-gray-200 rounded-full px-2 py-0.5 text-gray-500"
                    title={`Jev の確信度 ${Math.round((meal.categoryConfidence ?? 0) * 100)}%`}
                  >
                    {MEAL_CATEGORIES[meal.category].emoji} {meal.category}
                  </span>
                ) : classifyingIds.includes(meal.id) ? (
                  <span className="text-gray-300">判定中…</span>
                ) : null}
              </span>
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
