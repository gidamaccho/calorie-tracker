type Props = {
  total: number;
  goal: number;
};

export const CalorieSummary = ({ total, goal }: Props) => {
  const percent = Math.min((total / goal) * 100, 100);
  const remaining = goal - total;

  const circumference = 2 * Math.PI * 54;
  const dashOffset = circumference - (percent / 100) * circumference;

  const color = percent >= 100 ? '#ef4444' : percent >= 80 ? '#f59e0b' : '#22c55e';

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6 flex flex-col items-center gap-3">
      <h2 className="text-lg font-semibold text-gray-700">今日のカロリー</h2>
      <div className="relative w-36 h-36">
        <svg className="w-full h-full -rotate-90" viewBox="0 0 120 120">
          <circle cx="60" cy="60" r="54" fill="none" stroke="#f0fdf4" strokeWidth="12" />
          <circle
            cx="60"
            cy="60"
            r="54"
            fill="none"
            stroke={color}
            strokeWidth="12"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={dashOffset}
            style={{ transition: 'stroke-dashoffset 0.5s ease' }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-3xl font-bold text-gray-800">{total.toLocaleString()}</span>
          <span className="text-xs text-gray-400">kcal</span>
        </div>
      </div>
      <div className="text-sm text-gray-500">
        {remaining > 0 ? (
          <span>あと <strong className="text-green-600">{remaining.toLocaleString()} kcal</strong></span>
        ) : (
          <span className="text-red-500 font-medium">目標を {Math.abs(remaining).toLocaleString()} kcal 超過</span>
        )}
        <span className="ml-1 text-gray-400">/ 目標 {goal.toLocaleString()} kcal</span>
      </div>
    </div>
  );
};
