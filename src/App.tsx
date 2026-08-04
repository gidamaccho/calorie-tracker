import { useState } from 'react';
import { useMeals } from './hooks/useMeals';
import { CalorieSummary } from './components/CalorieSummary';
import { MealForm } from './components/MealForm';
import { MealList } from './components/MealList';
import { TechnoScreen } from './components/TechnoScreen';

const DEFAULT_GOAL = 2000;

type Tab = 'calorie' | 'techno';

function App() {
  const [tab, setTab] = useState<Tab>('calorie');
  const { meals, addMeal, deleteMeal, totalCalories } = useMeals();
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
            <h1 className="text-xl font-bold text-gray-800">
              {tab === 'calorie' ? '🥗 カロリー管理' : '🎧 テクノ楽譜'}
            </h1>
            <p className="text-xs text-gray-400 mt-0.5">{today}</p>
          </div>
          <div className="flex items-center gap-2 text-sm text-gray-500">
            {tab === 'techno' ? null : editingGoal ? (
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
        <div className="max-w-md mx-auto px-4 pb-3">
          <div className="flex gap-1 bg-gray-100 rounded-xl p-1">
            {([
              ['calorie', '🥗 カロリー'],
              ['techno', '🎧 テクノ'],
            ] as const).map(([id, label]) => (
              <button
                key={id}
                onClick={() => setTab(id)}
                className={[
                  'flex-1 text-sm py-2.5 rounded-lg transition-colors min-h-[44px]',
                  tab === id ? 'bg-white text-gray-800 font-medium shadow-sm' : 'text-gray-500',
                ].join(' ')}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </header>

      <main className="max-w-md mx-auto px-4 py-6 flex flex-col gap-4 safe-x safe-bottom">
        {tab === 'calorie' ? (
          <>
            <CalorieSummary total={totalCalories} goal={goal} />
            <MealForm onAdd={addMeal} />
            <MealList meals={meals} onDelete={deleteMeal} />
          </>
        ) : (
          <TechnoScreen />
        )}
      </main>
    </div>
  );
}

export default App;
