"use client";

import { useEffect, useRef } from "react";

export default function TumorFilm() {
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (!motion.matches) void video.play().catch(() => {});

    function pauseOnReducedMotion(event: MediaQueryListEvent) {
      if (event.matches) video?.pause();
    }

    motion.addEventListener("change", pauseOnReducedMotion);
    return () => motion.removeEventListener("change", pauseOnReducedMotion);
  }, []);

  return (
    <video
      ref={videoRef}
      id="tumor-film"
      controls
      muted
      playsInline
      preload="metadata"
      poster="/landing/lung1-002.png"
      width={512}
      height={512}
      aria-label="LUNG1-002 scan, contour reconstruction, rotating mask, and four measured features"
    >
      <source src="/landing/tumor-workflow.mp4" type="video/mp4" />
      <a href="/landing/tumor-workflow.mp4">Watch the scan animation</a>
    </video>
  );
}
