/**
 * TypeSafe AI の System One モデル "Jev" を呼び出す最小クライアント。
 *
 * Jev は文章を生成せず、渡した state と型付きの questions に対して
 * 選択肢とその確率（calibrated probability）だけを返す判定特化モデル。
 * 公式SDK (@typesafe-ai/sdk) は Node 20+ 前提のため、ブラウザからは fetch で直接呼ぶ。
 *
 * @see https://typesafe.ai/blog/introducing-system-one-models-and-jev
 */

const ENDPOINT = 'https://api.typesafe.ai/v1/systemone';
const MODEL = 'jev-latest';
const TIMEOUT_MS = 10_000;

/** 判定させたい問い。choice は選択肢名 -> 補足説明（不要なら null）。 */
export type JevQuestion =
  | { type: 'noul'; instructions: string }
  | { type: 'choice'; instructions: string; criteria: Record<string, string | null> };

/** noul は P(yes) の確率のみ。choice は選ばれた選択肢・全選択肢の確率・確信度。 */
export type JevAnswer =
  | { type: 'noul'; noul: number }
  | { type: 'choice'; choice: string; probabilities: Record<string, number>; confidence: number };

export type JevUsage = { input_tokens: number; output_tokens: number };

export type JevResponse = {
  model: string;
  answers: Record<string, JevAnswer>;
  usage?: JevUsage;
  requestId: string | null;
};

export type JevErrorKind = 'auth' | 'rate_limit' | 'timeout' | 'network' | 'server' | 'invalid_response';

export class JevError extends Error {
  readonly kind: JevErrorKind;
  readonly status?: number;
  readonly requestId?: string | null;

  constructor(kind: JevErrorKind, message: string, status?: number, requestId?: string | null) {
    super(message);
    this.name = 'JevError';
    this.kind = kind;
    this.status = status;
    this.requestId = requestId;
  }
}

/** 画面にそのまま出せる日本語メッセージ。 */
export const jevErrorMessage = (error: unknown): string => {
  if (!(error instanceof JevError)) return 'Jev の判定に失敗しました';
  switch (error.kind) {
    case 'auth':
      return 'Jev の APIキーが無効です。設定を確認してください';
    case 'rate_limit':
      return 'Jev のレート制限に達しました。少し待って再試行してください';
    case 'timeout':
      return 'Jev の応答がタイムアウトしました';
    case 'network':
      return 'Jev に接続できませんでした';
    case 'server':
      return `Jev がエラーを返しました (HTTP ${error.status ?? '?'})`;
    case 'invalid_response':
      return 'Jev のレスポンスを解釈できませんでした';
  }
};

const parseAnswer = (value: unknown): JevAnswer | null => {
  if (typeof value !== 'object' || value === null) return null;
  const raw = value as Record<string, unknown>;

  if (raw.type === 'noul' && typeof raw.noul === 'number') {
    return { type: 'noul', noul: raw.noul };
  }
  if (raw.type === 'choice' && typeof raw.choice === 'string') {
    const probabilities: Record<string, number> = {};
    if (typeof raw.probabilities === 'object' && raw.probabilities !== null) {
      for (const [key, p] of Object.entries(raw.probabilities)) {
        if (typeof p === 'number') probabilities[key] = p;
      }
    }
    return {
      type: 'choice',
      choice: raw.choice,
      probabilities,
      confidence: typeof raw.confidence === 'number' ? raw.confidence : 0,
    };
  }
  return null;
};

export type AskOptions = {
  apiKey: string;
  /** 判定の材料となるアプリ側の状態。Jev はこれを読んで選択肢の確率を返す。 */
  state: string;
  questions: Record<string, JevQuestion>;
  signal?: AbortSignal;
};

/** Jev に問いを投げ、型付きの答えを受け取る。 */
export const ask = async ({ apiKey, state, questions, signal }: AskOptions): Promise<JevResponse> => {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  const onAbort = () => controller.abort();
  signal?.addEventListener('abort', onAbort);

  let response: Response;
  try {
    response = await fetch(ENDPOINT, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${apiKey}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ model: MODEL, state, questions }),
      signal: controller.signal,
    });
  } catch (cause) {
    // 呼び出し側が中断した場合は、そのまま中断として伝える。
    if (signal?.aborted) throw cause;
    if (controller.signal.aborted) {
      throw new JevError('timeout', `Jev が ${TIMEOUT_MS}ms 以内に応答しませんでした`);
    }
    throw new JevError('network', 'Jev への接続に失敗しました');
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener('abort', onAbort);
  }

  const requestId = response.headers.get('x-typesafe-request-id');

  if (!response.ok) {
    const kind: JevErrorKind =
      response.status === 401 || response.status === 403
        ? 'auth'
        : response.status === 429
          ? 'rate_limit'
          : 'server';
    throw new JevError(kind, `Jev が HTTP ${response.status} を返しました`, response.status, requestId);
  }

  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new JevError('invalid_response', 'Jev のレスポンスが JSON ではありませんでした', response.status, requestId);
  }

  const raw = body as { model?: unknown; answers?: unknown; usage?: unknown };
  if (typeof raw.answers !== 'object' || raw.answers === null) {
    throw new JevError('invalid_response', 'Jev のレスポンスに answers がありません', response.status, requestId);
  }

  const answers: Record<string, JevAnswer> = {};
  for (const [key, value] of Object.entries(raw.answers as Record<string, unknown>)) {
    const answer = parseAnswer(value);
    if (answer) answers[key] = answer;
  }

  return {
    model: typeof raw.model === 'string' ? raw.model : MODEL,
    answers,
    usage: raw.usage as JevUsage | undefined,
    requestId,
  };
};
