"use client";

import { useEffect, useRef, useState } from "react";
import { Camera, CircleAlert } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

const CARD_RATIO = 63 / 88;

type CameraCaptureProps = {
  onCapture: (blob: Blob) => void;
  onCancel: () => void;
};

export function CameraCapture({ onCapture, onCancel }: CameraCaptureProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function start() {
      if (!window.isSecureContext && window.location.hostname !== "localhost") {
        setError(
          "Camera access needs HTTPS. Use the local HTTPS port and trust the Caddy certificate on this phone.",
        );
        return;
      }
      if (!navigator.mediaDevices?.getUserMedia) {
        setError("This browser cannot open the camera. Upload a photograph instead.");
        return;
      }
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: "environment" }, width: { ideal: 1920 } },
          audio: false,
        });
        if (cancelled) {
          stream.getTracks().forEach((track) => track.stop());
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play();
        }
      } catch (cause) {
        const name = cause instanceof DOMException ? cause.name : "";
        if (name === "NotAllowedError") {
          setError("Camera permission was denied. Allow camera access or upload a photo.");
        } else if (name === "NotFoundError") {
          setError("No camera was found on this device.");
        } else {
          setError("Could not open the camera. Upload a photograph instead.");
        }
      }
    }
    void start();
    return () => {
      cancelled = true;
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    };
  }, []);

  async function capture() {
    const video = videoRef.current;
    if (!video || video.videoWidth === 0) {
      return;
    }
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const context = canvas.getContext("2d");
    if (!context) {
      return;
    }
    context.drawImage(video, 0, 0);
    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, "image/jpeg", 0.92),
    );
    if (blob) {
      streamRef.current?.getTracks().forEach((track) => track.stop());
      onCapture(blob);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      {error ? (
        <Alert variant="destructive">
          <CircleAlert />
          <AlertTitle>Camera unavailable</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : (
        <div className="relative overflow-hidden rounded-xl bg-black">
          <video
            ref={videoRef}
            className="aspect-[3/4] w-full object-cover"
            playsInline
            muted
            aria-label="Live camera preview"
          />
          <div
            className="pointer-events-none absolute inset-0 flex items-center justify-center"
            aria-hidden="true"
          >
            <div
              className="rounded-md border-2 border-white/80 shadow-[0_0_0_999px_rgba(0,0,0,0.35)]"
              style={{ width: "70%", aspectRatio: CARD_RATIO }}
            />
          </div>
        </div>
      )}
      <div className="flex gap-3">
        <Button
          type="button"
          variant="outline"
          className="h-11 min-h-11 flex-1"
          onClick={onCancel}
        >
          Cancel
        </Button>
        <Button
          type="button"
          className="h-11 min-h-11 flex-1"
          onClick={() => void capture()}
          disabled={Boolean(error)}
        >
          <Camera data-icon="inline-start" />
          Capture
        </Button>
      </div>
    </div>
  );
}
