import { useState } from 'react';
import { useMeals } from './hooks/useMeals';
import { useJevKey } from './hooks/useJevKey';
import { useMealClassifier } from './hooks/useMealClassifier';
import { CalorieSummary } from './components/CalorieSummary';
import { MealForm } from './components/MealForm';
import { MealList } from './components/MealList';
import { JevSettings } from './components/JevSettings';

const DEFAULT_GOAL = 2000;

function App() {
  const { meals, addMeal, deleteMeal, setMealCategory, totalCalories } = useMeals();
  const { apiKey, saveKey } = useJevKey();
  const { classify, pendingIds, error: jevError, dismissError } = useMealClassifier(
    apiKey,
    setMealCategory,
  );

  const handleAddMeal = (name: string, calories: number) => {
    classify(addMeal(name, calories));
  };
  const [goal, setGoal] = useState(() => {
    const saved = localStorage.getItem('calorie-goal');
    return saved ? parseInt(saved, 10) : DEFAULT_GOAL;
  });
  const [editingGoal, setEditingGoal] = useState(false);
  const [goalInput, setGoalInput] = useState(String(goal));

  const saveGoal = () => {
    const val = parseInt(goalInput, 10);
    if (!isNaN(val) && val > 0) {
      setGoal(val);
      localStorage.setItem('calorie-goal', String(val));
    }
    setEditingGoal(false);
  };

  const today = new Date().toLocaleDateString('ja-JP', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    weekday: 'short',
  });

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-100 shadow-sm safe-top safe-x">
        <div className="max-w-md mx-auto px-4 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-gray-800">🥗 カロリー管理</h1>
            <p className="text-xs text-gray-400 mt-0.5">{today}</p>
          </div>
          <div className="flex items-center gap-2 text-sm text-gray-500">
            {editingGoal ? (
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  inputMode="numeric"
                  value={goalInput}
                  onChange={e => setGoalInput(e.target.value)}
                  className="w-24 border border-gray-200 rounded-lg px-2 py-2 text-base outline-none focus:ring-2 focus:ring-green-400"
                  onKeyDown={e => e.key === 'Enter' && saveGoal()}
                  autoFocus
                />
                <span className="text-xs">kcal</span>
                <button
                  onClick={saveGoal}
                  className="bg-green-500 text-white text-sm px-3 py-2 rounded-lg hover:bg-green-600 active:bg-green-700 transition-colors min-w-[44px]"
                >
                  保存
                </button>
              </div>
            ) : (
              <button
                onClick={() => { setGoalInput(String(goal)); setEditingGoal(true); }}
                className="text-xs bg-gray-100 active:bg-gray-200 px-3 py-2 rounded-lg transition-colors min-h-[44px]"
              >
                目標: {goal.toLocaleString()} kcal
              </button>
            )}
          </div>
        </div>
      </header>

      <main className="max-w-md mx-auto px-4 py-6 flex flex-col gap-4 safe-x safe-bottom">
        <CalorieSummary total={totalCalories} goal={goal} />
        <MealForm onAdd={handleAddMeal} />
        {jevError && (
          <div className="flex items-center justify-between gap-3 bg-amber-50 border border-amber-100 text-amber-700 rounded-xl px-4 py-3 text-sm">
            <span>{jevError}</span>
            <button
              onClick={dismissError}
              className="flex items-center justify-center w-8 h-8 rounded-full text-amber-400 active:bg-amber-100 transition-colors shrink-0"
              aria-label="閉じる"
            >
              ✕
            </button>
          </div>
        )}
        <MealList meals={meals} onDelete={deleteMeal} classifyingIds={pendingIds} />
        <JevSettings apiKey={apiKey} onSave={saveKey} />
      </main>
    </div>
  );
}

export default App;
