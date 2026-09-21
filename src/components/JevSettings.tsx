import { useState } from 'react';

type Props = {
  apiKey: string;
  onSave: (key: string) => void;
};

/**
 * Jev の APIキーを利用者自身に入力してもらう（BYOK）。
 * キーはこの端末の localStorage にだけ保存し、リポジトリにもビルド成果物にも含めない。
 */
export const JevSettings = ({ apiKey, onSave }: Props) => {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState(apiKey);

  const hasKey = apiKey.length > 0;

  const handleSave = () => {
    onSave(input);
    setOpen(false);
  };

  const handleClear = () => {
    setInput('');
    onSave('');
  };

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center justify-between text-left min-h-[44px]"
        aria-expanded={open}
      >
        <span className="flex items-center gap-2">
          <span className="text-lg font-semibold text-gray-700">⚡ Jev 自動分類</span>
          <span
            className={`text-xs px-2 py-0.5 rounded-full ${
              hasKey ? 'bg-green-50 text-green-600' : 'bg-gray-100 text-gray-400'
            }`}
          >
            {hasKey ? '有効' : '未設定'}
          </span>
        </span>
        <span className="text-gray-300 text-sm">{open ? '閉じる' : '設定'}</span>
      </button>

      {open && (
        <div className="mt-4 flex flex-col gap-3">
          <p className="text-xs text-gray-500 leading-relaxed">
            TypeSafe AI の判定モデル Jev で、追加した食事を主食・主菜・副菜などに自動で分類します。
            APIキーはこの端末のブラウザにのみ保存され、どこにも送信されません
            （判定時に api.typesafe.ai へ直接送られます）。
          </p>
          <input
            type="password"
            placeholder="Jev の APIキー"
            value={input}
            onChange={e => setInput(e.target.value)}
            autoComplete="off"
            className="border border-gray-200 rounded-xl px-4 py-3 text-base outline-none focus:ring-2 focus:ring-green-400 focus:border-transparent transition"
          />
          <div className="flex gap-2">
            <button
              onClick={handleSave}
              className="flex-1 bg-green-500 hover:bg-green-600 active:bg-green-700 text-white font-medium py-3 rounded-xl transition-colors min-h-[48px]"
            >
              保存
            </button>
            {hasKey && (
              <button
                onClick={handleClear}
                className="px-4 text-sm text-gray-400 active:text-red-400 rounded-xl transition-colors min-h-[48px]"
              >
                削除
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
