/** Claude に送る前に写真を縮小する。スマホの原寸写真は数MBあり、そのままでは遅く高くつく。 */

const MAX_EDGE = 1024;
const QUALITY = 0.8;

export type PreparedImage = {
  /** data: プレフィックスを除いた base64 本体。 */
  base64: string;
  mediaType: 'image/jpeg';
  /** 画面プレビュー用の data URL。 */
  previewUrl: string;
};

const loadImage = (file: File): Promise<HTMLImageElement> =>
  new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      resolve(img);
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error('画像を読み込めませんでした'));
    };
    img.src = url;
  });

/** 長辺 1024px の JPEG に変換する。 */
export const prepareImage = async (file: File): Promise<PreparedImage> => {
  const img = await loadImage(file);

  const scale = Math.min(1, MAX_EDGE / Math.max(img.width, img.height));
  const width = Math.round(img.width * scale);
  const height = Math.round(img.height * scale);

  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;

  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('画像を変換できませんでした');
  ctx.drawImage(img, 0, 0, width, height);

  const previewUrl = canvas.toDataURL('image/jpeg', QUALITY);
  return {
    base64: previewUrl.slice(previewUrl.indexOf(',') + 1),
    mediaType: 'image/jpeg',
    previewUrl,
  };
};
