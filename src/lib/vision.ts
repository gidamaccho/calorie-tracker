/**
 * 食事の写真を Claude に読ませ、食品名と推定カロリーを構造化して取り出す。
 *
 * Jev は判定専用モデルで画像を受け取れない（state は文字列・JSON・配列のみ）ため、
 * 写真はここでテキスト化し、その結果を Jev に渡して区分を判定させる。
 */
import type { PreparedImage } from './image';

const MODEL = 'claude-opus-5';

const SYSTEM = `あなたは管理栄養士です。食事の写真から、食事記録に必要な情報だけを抽出します。

- 写っている料理をすべて挙げ、一般的な一人前を基準に総カロリーを推定する
- 器・箸・カトラリーの大きさを手がかりに分量を見積もる
- 食べ物が写っていない場合は items を空配列、calories を 0 にする
- 推測できない場合でも必ずスキーマ通りに答える`;

/** structured outputs でこの形を保証させる。 */
const SCHEMA = {
  type: 'object',
  properties: {
    items: {
      type: 'array',
      items: { type: 'string' },
      description: '写真に写っている料理名。食べ物がなければ空配列。',
    },
    name: {
      type: 'string',
      description: '食事記録に使う短い名前（例: 鮭の塩焼き定食）',
    },
    calories: {
      type: 'integer',
      description: '推定される総カロリー（kcal）',
    },
    note: {
      type: 'string',
      description: '分量をどう見積もったかの短い根拠',
    },
  },
  required: ['items', 'name', 'calories', 'note'],
  additionalProperties: false,
} as const;

export type MealPhotoReading = {
  items: string[];
  name: string;
  calories: number;
  note: string;
};

export type VisionErrorKind = 'auth' | 'rate_limit' | 'refusal' | 'no_food' | 'network' | 'server' | 'invalid_response';

export class VisionError extends Error {
  readonly kind: VisionErrorKind;

  constructor(kind: VisionErrorKind, message: string) {
    super(message);
    this.name = 'VisionError';
    this.kind = kind;
  }
}

export const visionErrorMessage = (error: unknown): string => {
  if (error instanceof VisionError) {
    switch (error.kind) {
      case 'auth':
        return 'Claude の APIキーが無効です。設定を確認してください';
      case 'rate_limit':
        return 'Claude のレート制限に達しました。少し待って再試行してください';
      case 'refusal':
        return 'この画像は解析できませんでした';
      case 'no_food':
        return '写真から食べ物を認識できませんでした。手入力してください';
      case 'network':
        return 'Claude に接続できませんでした';
      case 'server':
        return 'Claude がエラーを返しました';
      case 'invalid_response':
        return 'Claude のレスポンスを解釈できませんでした';
    }
  }
  return '写真の解析に失敗しました';
};

const parseReading = (raw: unknown): MealPhotoReading => {
  if (typeof raw !== 'object' || raw === null) {
    throw new VisionError('invalid_response', 'JSON オブジェクトではありません');
  }
  const value = raw as Record<string, unknown>;
  const items = Array.isArray(value.items) ? value.items.filter((i): i is string => typeof i === 'string') : [];
  const calories = typeof value.calories === 'number' ? Math.max(0, Math.round(value.calories)) : 0;
  const name = typeof value.name === 'string' ? value.name.trim() : '';

  if (items.length === 0 || calories <= 0 || !name) {
    throw new VisionError('no_food', '写真から食事を読み取れませんでした');
  }

  return {
    items,
    name,
    calories,
    note: typeof value.note === 'string' ? value.note : '',
  };
};

/** 写真1枚から食品名と推定カロリーを読み取る。 */
export const readMealPhoto = async (
  image: PreparedImage,
  apiKey: string,
  signal?: AbortSignal,
): Promise<MealPhotoReading> => {
  // SDK はこのアプリ本体より大きいので、写真を使うときだけ読み込む。
  const { default: Anthropic } = await import('@anthropic-ai/sdk');

  const client = new Anthropic({
    apiKey,
    // 利用者自身のキーをブラウザから直接使う（BYOK）ため明示的に許可する。
    dangerouslyAllowBrowser: true,
  });

  let response;
  try {
    response = await client.messages.create(
      {
        model: MODEL,
        max_tokens: 16000,
        system: SYSTEM,
        // effort はここが精度と待ち時間のつまみ。写真1枚の読み取りなので medium から。
        output_config: {
          effort: 'medium',
          format: { type: 'json_schema', schema: SCHEMA },
        },
        messages: [
          {
            role: 'user',
            content: [
              {
                type: 'image',
                source: { type: 'base64', media_type: image.mediaType, data: image.base64 },
              },
              { type: 'text', text: 'この食事の内容と推定カロリーを教えてください。' },
            ],
          },
        ],
      },
      { signal },
    );
  } catch (error) {
    if (signal?.aborted) throw error;
    if (error instanceof Anthropic.AuthenticationError || error instanceof Anthropic.PermissionDeniedError) {
      throw new VisionError('auth', 'APIキーが拒否されました');
    }
    if (error instanceof Anthropic.RateLimitError) {
      throw new VisionError('rate_limit', 'レート制限に達しました');
    }
    if (error instanceof Anthropic.APIConnectionError) {
      throw new VisionError('network', 'Claude に接続できませんでした');
    }
    if (error instanceof Anthropic.APIError) {
      throw new VisionError('server', `Claude が ${error.status ?? ''} を返しました`);
    }
    throw new VisionError('server', '不明なエラーが発生しました');
  }

  if (response.stop_reason === 'refusal') {
    throw new VisionError('refusal', 'モデルが解析を拒否しました');
  }

  const text = response.content.find(block => block.type === 'text');
  if (!text) {
    throw new VisionError('invalid_response', 'テキストブロックがありません');
  }

  try {
    return parseReading(JSON.parse(text.text));
  } catch (error) {
    if (error instanceof VisionError) throw error;
    throw new VisionError('invalid_response', 'JSON として解釈できませんでした');
  }
};
