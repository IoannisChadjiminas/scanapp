export const CARD_RATIO = 63 / 88;

export type Rect = { x: number; y: number; w: number; h: number };

export function coverSourceRect(
  sourceW: number,
  sourceH: number,
  viewW: number,
  viewH: number,
): Rect {
  if (sourceW <= 0 || sourceH <= 0 || viewW <= 0 || viewH <= 0) {
    return { x: 0, y: 0, w: sourceW, h: sourceH };
  }
  const sourceRatio = sourceW / sourceH;
  const viewRatio = viewW / viewH;
  if (sourceRatio > viewRatio) {
    const h = sourceH;
    const w = sourceH * viewRatio;
    return { x: (sourceW - w) / 2, y: 0, w, h };
  }
  const w = sourceW;
  const h = sourceW / viewRatio;
  return { x: 0, y: (sourceH - h) / 2, w, h };
}

export function containDestRect(
  sourceW: number,
  sourceH: number,
  viewW: number,
  viewH: number,
): Rect {
  if (sourceW <= 0 || sourceH <= 0 || viewW <= 0 || viewH <= 0) {
    return { x: 0, y: 0, w: viewW, h: viewH };
  }
  const scale = Math.min(viewW / sourceW, viewH / sourceH);
  const w = sourceW * scale;
  const h = sourceH * scale;
  return { x: (viewW - w) / 2, y: (viewH - h) / 2, w, h };
}

export function cardGuideInView(viewW: number, viewH: number, widthFraction = 0.78): Rect {
  let w = viewW * widthFraction;
  let h = w / CARD_RATIO;
  if (h > viewH * 0.92) {
    h = viewH * 0.92;
    w = h * CARD_RATIO;
  }
  return { x: (viewW - w) / 2, y: (viewH - h) / 2, w, h };
}

export function viewRectToSource(
  view: Rect,
  cover: Rect,
  viewW: number,
): Rect {
  const scale = cover.w / viewW;
  return {
    x: cover.x + view.x * scale,
    y: cover.y + view.y * scale,
    w: view.w * scale,
    h: view.h * scale,
  };
}

export function clampRect(rect: Rect, boundW: number, boundH: number): Rect {
  const w = Math.max(1, Math.min(rect.w, boundW));
  const h = Math.max(1, Math.min(rect.h, boundH));
  const x = Math.max(0, Math.min(rect.x, boundW - w));
  const y = Math.max(0, Math.min(rect.y, boundH - h));
  return { x, y, w, h };
}
