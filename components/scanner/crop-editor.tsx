"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { RotateCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { containDestRect, type Rect } from "@/lib/image-frame";

type Crop = { x: number; y: number; w: number; h: number };
type DragMode = "move" | "nw" | "ne" | "sw" | "se";

type CropEditorProps = {
  src: string;
  onConfirm: (blob: Blob) => void;
  onRetry: () => void;
};

const MIN_CROP = 0.28;

export function CropEditor({ src, onConfirm, onRetry }: CropEditorProps) {
  const imageRef = useRef<HTMLImageElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const [rotation, setRotation] = useState(0);
  const [crop, setCrop] = useState<Crop>({ x: 0.02, y: 0.02, w: 0.96, h: 0.96 });
  const [frame, setFrame] = useState<Rect>({ x: 0, y: 0, w: 0, h: 0 });
  const drag = useRef<{
    mode: DragMode;
    startX: number;
    startY: number;
    crop: Crop;
  } | null>(null);

  const measure = useCallback(() => {
    const stage = stageRef.current;
    const image = imageRef.current;
    if (!stage || !image || !image.naturalWidth) {
      return;
    }
    const bounds = stage.getBoundingClientRect();
    setFrame(containDestRect(image.naturalWidth, image.naturalHeight, bounds.width, bounds.height));
  }, []);

  useEffect(() => {
    const stage = stageRef.current;
    if (!stage) {
      return;
    }
    const observer = new ResizeObserver(() => measure());
    observer.observe(stage);
    return () => observer.disconnect();
  }, [measure, src]);

  function onPointerDown(event: React.PointerEvent<HTMLDivElement>, mode: DragMode) {
    event.currentTarget.setPointerCapture(event.pointerId);
    event.stopPropagation();
    drag.current = { mode, startX: event.clientX, startY: event.clientY, crop };
  }

  function onPointerMove(event: React.PointerEvent<HTMLDivElement>) {
    if (!drag.current || !frame.w || !frame.h) {
      return;
    }
    const dx = (event.clientX - drag.current.startX) / frame.w;
    const dy = (event.clientY - drag.current.startY) / frame.h;
    const start = drag.current.crop;
    let next = { ...start };
    if (drag.current.mode === "move") {
      next.x = Math.min(1 - start.w, Math.max(0, start.x + dx));
      next.y = Math.min(1 - start.h, Math.max(0, start.y + dy));
    } else {
      if (drag.current.mode.includes("w")) {
        const x = Math.min(start.x + start.w - MIN_CROP, Math.max(0, start.x + dx));
        next.w = start.w + (start.x - x);
        next.x = x;
      }
      if (drag.current.mode.includes("e")) {
        next.w = Math.min(1 - start.x, Math.max(MIN_CROP, start.w + dx));
      }
      if (drag.current.mode.includes("n")) {
        const y = Math.min(start.y + start.h - MIN_CROP, Math.max(0, start.y + dy));
        next.h = start.h + (start.y - y);
        next.y = y;
      }
      if (drag.current.mode.includes("s")) {
        next.h = Math.min(1 - start.y, Math.max(MIN_CROP, start.h + dy));
      }
    }
    setCrop(next);
  }

  function onPointerUp() {
    drag.current = null;
  }

  async function confirm() {
    const image = imageRef.current;
    if (!image) {
      return;
    }
    const width = image.naturalWidth;
    const height = image.naturalHeight;
    const sx = Math.round(crop.x * width);
    const sy = Math.round(crop.y * height);
    const sw = Math.max(1, Math.round(crop.w * width));
    const sh = Math.max(1, Math.round(crop.h * height));
    const canvas = document.createElement("canvas");
    const context = canvas.getContext("2d");
    if (!context) {
      return;
    }
    if (rotation) {
      canvas.width = rotation % 180 === 0 ? sw : sh;
      canvas.height = rotation % 180 === 0 ? sh : sw;
      context.translate(canvas.width / 2, canvas.height / 2);
      context.rotate((rotation * Math.PI) / 180);
      context.drawImage(image, sx, sy, sw, sh, -sw / 2, -sh / 2, sw, sh);
    } else {
      canvas.width = sw;
      canvas.height = sh;
      context.drawImage(image, sx, sy, sw, sh, 0, 0, sw, sh);
    }
    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, "image/jpeg", 0.95),
    );
    if (blob) {
      onConfirm(blob);
    }
  }

  const handles: DragMode[] = ["nw", "ne", "sw", "se"];

  return (
    <div className="flex flex-col gap-4">
      <div ref={stageRef} className="relative overflow-hidden rounded-xl bg-muted">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          ref={imageRef}
          src={src}
          alt="Captured card photograph"
          className="mx-auto max-h-[70vh] w-full object-contain"
          style={{ transform: `rotate(${rotation}deg)` }}
          onLoad={measure}
        />
        {frame.w > 0 ? (
          <div
            role="slider"
            aria-label="Card crop box. Drag to reposition, use corners to resize."
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(crop.x * 100)}
            tabIndex={0}
            className="absolute cursor-move rounded-sm border-2 border-primary bg-primary/10"
            style={{
              left: frame.x + crop.x * frame.w,
              top: frame.y + crop.y * frame.h,
              width: crop.w * frame.w,
              height: crop.h * frame.h,
            }}
            onPointerDown={(event) => onPointerDown(event, "move")}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onPointerCancel={onPointerUp}
          >
            {handles.map((mode) => (
              <div
                key={mode}
                className="absolute size-6 rounded-full border-2 border-primary bg-background"
                style={{
                  left: mode.includes("w") ? -12 : undefined,
                  right: mode.includes("e") ? -12 : undefined,
                  top: mode.includes("n") ? -12 : undefined,
                  bottom: mode.includes("s") ? -12 : undefined,
                  cursor:
                    mode === "nw" || mode === "se" ? "nwse-resize" : "nesw-resize",
                }}
                onPointerDown={(event) => onPointerDown(event, mode)}
                onPointerMove={onPointerMove}
                onPointerUp={onPointerUp}
                onPointerCancel={onPointerUp}
              />
            ))}
          </div>
        ) : null}
      </div>
      <p className="text-sm text-muted-foreground">
        Drag the box onto the card. Use the corners to tighten the crop.
      </p>
      <div className="flex flex-wrap gap-3">
        <Button
          type="button"
          variant="outline"
          className="h-11 min-h-11 flex-1"
          onClick={onRetry}
        >
          Retry
        </Button>
        <Button
          type="button"
          variant="secondary"
          className="h-11 min-h-11"
          onClick={() => setRotation((value) => (value + 90) % 360)}
        >
          <RotateCw data-icon="inline-start" />
          Rotate
        </Button>
        <Button type="button" className="h-11 min-h-11 flex-1" onClick={() => void confirm()}>
          Scan crop
        </Button>
      </div>
    </div>
  );
}
