import { useState, useEffect } from 'react';
import type { Meal } from '../types';
import type { MealCategory } from '../lib/mealCategory';

const getTodayKey = () => new Date().toISOString().slice(0, 10);

const loadMeals = (): Meal[] => {
  try {
    const raw = localStorage.getItem(`meals-${getTodayKey()}`);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
};

export const useMeals = () => {
  const [meals, setMeals] = useState<Meal[]>(loadMeals);

  useEffect(() => {
    localStorage.setItem(`meals-${getTodayKey()}`, JSON.stringify(meals));
  }, [meals]);

  const addMeal = (name: string, calories: number): Meal => {
    const meal: Meal = {
      id: crypto.randomUUID(),
      name,
      calories,
      time: new Date().toISOString(),
    };
    setMeals(prev => [...prev, meal]);
    return meal;
  };

  const setMealCategory = (id: string, category: MealCategory, confidence: number) => {
    setMeals(prev =>
      prev.map(m => (m.id === id ? { ...m, category, categoryConfidence: confidence } : m)),
    );
  };

  const deleteMeal = (id: string) => {
    setMeals(prev => prev.filter(m => m.id !== id));
  };

  const totalCalories = meals.reduce((sum, m) => sum + m.calories, 0);

  return { meals, addMeal, deleteMeal, setMealCategory, totalCalories };
};
