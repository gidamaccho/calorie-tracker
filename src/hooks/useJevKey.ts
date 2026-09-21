import { useState } from 'react';

const STORAGE_KEY = 'jev-api-key';

const loadKey = (): string => {
  try {
    return localStorage.getItem(STORAGE_KEY) ?? '';
  } catch {
    return '';
  }
};

/**
 * Jev の APIキーを端末のブラウザにだけ保持する（BYOK）。
 * このアプリはバックエンドを持たない静的サイトなので、キーはビルド成果物には含めず
 * 利用者自身に入力してもらう。
 */
export const useJevKey = () => {
  const [apiKey, setApiKey] = useState<string>(loadKey);

  const saveKey = (key: string) => {
    const trimmed = key.trim();
    setApiKey(trimmed);
    try {
      if (trimmed) localStorage.setItem(STORAGE_KEY, trimmed);
      else localStorage.removeItem(STORAGE_KEY);
    } catch {
      // プライベートモードなどで保存できない場合もこのセッション中は使えるようにする。
    }
  };

  return { apiKey, saveKey, hasKey: apiKey.length > 0 };
};
