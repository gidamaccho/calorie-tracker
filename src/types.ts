import type { MealCategory } from './lib/mealCategory';

export type Meal = {
  id: string;
  name: string;
  calories: number;
  time: string;
  /** Jev が判定した献立の区分。未判定・確信度が低い場合は付かない。 */
  category?: MealCategory;
  categoryConfidence?: number;
};
