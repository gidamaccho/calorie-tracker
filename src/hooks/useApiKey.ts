import { useState } from 'react';

const load = (storageKey: string): string => {
  try {
    return localStorage.getItem(storageKey) ?? '';
  } catch {
    return '';
  }
};

/**
 * APIキーを端末のブラウザにだけ保持する（BYOK）。
 * このアプリはバックエンドを持たない静的サイトなので、キーはビルド成果物には含めず
 * 利用者自身に入力してもらう。
 */
export const useApiKey = (storageKey: string) => {
  const [apiKey, setApiKey] = useState<string>(() => load(storageKey));

  const saveKey = (key: string) => {
    const trimmed = key.trim();
    setApiKey(trimmed);
    try {
      if (trimmed) localStorage.setItem(storageKey, trimmed);
      else localStorage.removeItem(storageKey);
    } catch {
      // プライベートモードなどで保存できない場合もこのセッション中は使えるようにする。
    }
  };

  return { apiKey, saveKey, hasKey: apiKey.length > 0 };
};

/** 食事の区分を判定する Jev のキー。 */
export const useJevKey = () => useApiKey('jev-api-key');

/** 写真を読み取る Claude のキー。 */
export const useClaudeKey = () => useApiKey('claude-api-key');
