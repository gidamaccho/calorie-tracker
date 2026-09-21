import { ask, JevError } from './jev';

/** Jev に渡す選択肢。キーがそのままカテゴリ名、値が判定の手がかりになる説明。 */
export const MEAL_CATEGORIES = {
  主食: { emoji: '🍚', hint: 'ご飯・パン・麺・シリアルなど炭水化物が中心のもの' },
  主菜: { emoji: '🍖', hint: '肉・魚・卵・大豆製品などタンパク質が中心のおかず' },
  副菜: { emoji: '🥗', hint: '野菜・きのこ・海藻が中心のサラダや小鉢' },
  汁物: { emoji: '🍲', hint: '味噌汁・スープ・シチューなど汁気のあるもの' },
  間食: { emoji: '🍩', hint: 'お菓子・スイーツ・果物など食事の間に取るもの' },
  飲み物: { emoji: '🥤', hint: 'ジュース・コーヒー・牛乳・酒類などの飲料' },
  その他: { emoji: '🍽️', hint: '上記のどれにも当てはまらないもの' },
} as const;

export type MealCategory = keyof typeof MEAL_CATEGORIES;

const CATEGORY_NAMES = Object.keys(MEAL_CATEGORIES) as MealCategory[];

const isMealCategory = (value: string): value is MealCategory =>
  (CATEGORY_NAMES as string[]).includes(value);

/** これを下回る確信度の判定は採用せず、未分類のままにする。 */
const MIN_CONFIDENCE = 0.5;

export type Classification = {
  category: MealCategory;
  confidence: number;
};

/**
 * 食事の記録を Jev に投げて、どの区分の食事かを判定する。
 * 確信度が低いときは null を返し、誤ったタグを付けないようにする。
 */
export const classifyMeal = async (
  meal: { name: string; calories: number },
  apiKey: string,
  signal?: AbortSignal,
): Promise<Classification | null> => {
  const criteria = Object.fromEntries(
    CATEGORY_NAMES.map(name => [name, MEAL_CATEGORIES[name].hint]),
  );

  const response = await ask({
    apiKey,
    signal,
    state: `食事記録\n食品名: ${meal.name}\nカロリー: ${meal.calories} kcal`,
    questions: {
      category: {
        type: 'choice',
        instructions: 'この食事記録は献立のどの区分に当たるか判定してください。',
        criteria,
      },
    },
  });

  const answer = response.answers.category;
  if (!answer || answer.type !== 'choice') {
    throw new JevError('invalid_response', 'Jev から category の判定が返りませんでした');
  }
  if (!isMealCategory(answer.choice) || answer.confidence < MIN_CONFIDENCE) return null;

  return { category: answer.choice, confidence: answer.confidence };
};
