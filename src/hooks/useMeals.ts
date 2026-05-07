import { useState, useEffect } from 'react';
import type { Meal } from '../types';

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

  const addMeal = (name: string, calories: number) => {
    setMeals(prev => [
      ...prev,
      { id: crypto.randomUUID(), name, calories, time: new Date().toISOString() },
    ]);
  };

  const deleteMeal = (id: string) => {
    setMeals(prev => prev.filter(m => m.id !== id));
  };

  const totalCalories = meals.reduce((sum, m) => sum + m.calories, 0);

  return { meals, addMeal, deleteMeal, totalCalories };
};
