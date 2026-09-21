import { useState } from 'react';
import type { Meal } from '../types';
import type { MealCategory } from '../lib/mealCategory';
import { classifyMeal } from '../lib/mealCategory';
import { jevErrorMessage } from '../lib/jev';

type OnClassified = (id: string, category: MealCategory, confidence: number) => void;

/**
 * 追加された食事を Jev に投げてカテゴリを判定させる。
 * 判定はカロリー記録の妨げにならないよう非同期で走らせ、失敗しても記録自体は残す。
 */
export const useMealClassifier = (apiKey: string, onClassified: OnClassified) => {
  const [pendingIds, setPendingIds] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  const classify = (meal: Meal) => {
    if (!apiKey) return;

    setPendingIds(prev => [...prev, meal.id]);
    setError(null);

    classifyMeal(meal, apiKey)
      .then(result => {
        if (result) onClassified(meal.id, result.category, result.confidence);
      })
      .catch(e => setError(jevErrorMessage(e)))
      .finally(() => setPendingIds(prev => prev.filter(id => id !== meal.id)));
  };

  return {
    classify,
    pendingIds,
    error,
    dismissError: () => setError(null),
  };
};
