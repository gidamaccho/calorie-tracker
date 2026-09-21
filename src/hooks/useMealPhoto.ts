import { useState } from 'react';
import { prepareImage } from '../lib/image';
import { readMealPhoto, visionErrorMessage } from '../lib/vision';
import type { MealPhotoReading } from '../lib/vision';

export type MealPhotoState = {
  analyzing: boolean;
  previewUrl: string | null;
  reading: MealPhotoReading | null;
  error: string | null;
  analyze: (file: File) => Promise<MealPhotoReading | null>;
  reset: () => void;
};

/** 写真を縮小して Claude に読ませ、食品名と推定カロリーを受け取る。 */
export const useMealPhoto = (apiKey: string): MealPhotoState => {
  const [analyzing, setAnalyzing] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [reading, setReading] = useState<MealPhotoReading | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reset = () => {
    setPreviewUrl(null);
    setReading(null);
    setError(null);
  };

  const analyze = async (file: File) => {
    setAnalyzing(true);
    setError(null);
    setReading(null);

    try {
      const image = await prepareImage(file);
      setPreviewUrl(image.previewUrl);
      const result = await readMealPhoto(image, apiKey);
      setReading(result);
      return result;
    } catch (e) {
      setError(visionErrorMessage(e));
      return null;
    } finally {
      setAnalyzing(false);
    }
  };

  return { analyzing, previewUrl, reading, error, analyze, reset };
};
