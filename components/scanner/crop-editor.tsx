"use client";

import { useRef, useState } from "react";
import { RotateCw } from "lucide-react";

import { Button } from "@/components/ui/button";

type CropEditorProps = {
  src: string;
  onConfirm: (blob: Blob) => void;
  onRetry: () => void;
};

export function CropEditor({ src, onConfirm, onRetry }: CropEditorProps) {
  const imageRef = useRef<HTMLImageElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const [rotation, setRotation] = useState(0);
  const [crop, setCrop] = useState({ x: 0.03, y: 0.03, w: 0.94, h: 0.94 });
  const drag = useRef<{ startX: number; startY: number; crop: typeof crop } | null>(null);

  function onPointerDown(event: React.PointerEvent<HTMLDivElement>) {
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current = { startX: event.clientX, startY: event.clientY, crop };
  }

  function onPointerMove(event: React.PointerEvent<HTMLDivElement>) {
    if (!drag.current || !stageRef.current) {
      return;
    }
    const rect = stageRef.current.getBoundingClientRect();
    const dx = (event.clientX - drag.current.startX) / rect.width;
    const dy = (event.clientY - drag.current.startY) / rect.height;
    const nextX = Math.min(1 - drag.current.crop.w, Math.max(0, drag.current.crop.x + dx));
    const nextY = Math.min(1 - drag.current.crop.h, Math.max(0, drag.current.crop.y + dy));
    setCrop({ ...drag.current.crop, x: nextX, y: nextY });
  }

  function onPointerUp() {
    drag.current = null;
  }

  async function confirm() {
    const image = imageRef.current;
    if (!image) {
      return;
    }
    const canvas = document.createElement("canvas");
    const width = image.naturalWidth;
    const height = image.naturalHeight;
    const sx = Math.round(crop.x * width);
    const sy = Math.round(crop.y * height);
    const sw = Math.round(crop.w * width);
    const sh = Math.round(crop.h * height);
    canvas.width = sw;
    canvas.height = sh;
    const context = canvas.getContext("2d");
    if (!context) {
      return;
    }
    context.save();
    if (rotation) {
      canvas.width = rotation % 180 === 0 ? sw : sh;
      canvas.height = rotation % 180 === 0 ? sh : sw;
      context.translate(canvas.width / 2, canvas.height / 2);
      context.rotate((rotation * Math.PI) / 180);
      context.drawImage(image, sx, sy, sw, sh, -sw / 2, -sh / 2, sw, sh);
    } else {
      context.drawImage(image, sx, sy, sw, sh, 0, 0, sw, sh);
    }
    context.restore();
    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, "image/jpeg", 0.92),
    );
    if (blob) {
      onConfirm(blob);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div
        ref={stageRef}
        className="relative overflow-hidden rounded-xl bg-muted"
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          ref={imageRef}
          src={src}
          alt="Captured card photograph"
          className="mx-auto max-h-[70vh] w-full object-contain"
          style={{ transform: `rotate(${rotation}deg)` }}
        />
        <div
          role="slider"
          aria-label="Card crop box. Drag to reposition."
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(crop.x * 100)}
          tabIndex={0}
          className="absolute cursor-move rounded-sm border-2 border-primary bg-primary/10"
          style={{
            left: `${crop.x * 100}%`,
            top: `${crop.y * 100}%`,
            width: `${crop.w * 100}%`,
            height: `${Math.min(crop.h, 1 - crop.y) * 100}%`,
          }}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
        />
      </div>
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
