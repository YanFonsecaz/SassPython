let _webpSupportCache: boolean | null = null;

function supportsWebp(): boolean {
  if (_webpSupportCache !== null) return _webpSupportCache;
  try {
    const c = document.createElement("canvas");
    c.width = 1;
    c.height = 1;
    _webpSupportCache = c.toDataURL("image/webp").startsWith("data:image/webp");
  } catch {
    _webpSupportCache = false;
  }
  return _webpSupportCache;
}

export async function comprimirImagem(
  file: File,
  maxLado = 1600,
  quality = 0.8
): Promise<string> {
  const bitmap = await createImageBitmap(file);
  const escala = Math.min(1, maxLado / Math.max(bitmap.width, bitmap.height));
  const w = Math.round(bitmap.width * escala);
  const h = Math.round(bitmap.height * escala);
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  if (!ctx) return "";
  ctx.drawImage(bitmap, 0, 0, w, h);
  bitmap.close();

  const mimeType = supportsWebp() ? "image/webp" : "image/jpeg";
  return canvas.toDataURL(mimeType, quality);
}

export function isImageFile(file: File): boolean {
  return file.type.startsWith("image/");
}
