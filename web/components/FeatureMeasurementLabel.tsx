"use client";

import { useEffect, useId, useState, type MouseEvent, type FocusEvent } from "react";
import { featureDetails } from "../lib/featureLabels";

export default function FeatureMeasurementLabel({ name }: { name: string }) {
  const { label, unit, explanation } = featureDetails(name);
  const tooltipId = useId();
  const [anchor, setAnchor] = useState<DOMRect>();
  function show(event: MouseEvent<HTMLButtonElement> | FocusEvent<HTMLButtonElement>) {
    setAnchor(event.currentTarget.getBoundingClientRect());
  }

  useEffect(() => {
    if (!anchor) return;
    const hide = () => setAnchor(undefined);
    const handleEscape = (event: KeyboardEvent) => { if (event.key === "Escape") hide(); };
    window.addEventListener("keydown", handleEscape);
    window.addEventListener("scroll", hide, true);
    window.addEventListener("resize", hide);
    return () => {
      window.removeEventListener("keydown", handleEscape);
      window.removeEventListener("scroll", hide, true);
      window.removeEventListener("resize", hide);
    };
  }, [anchor]);

  return <>
    <span>{label} <small className="feature-unit">({unit})</small></span>
    <button type="button" className="feature-info" aria-label={`About ${label}`}
      aria-describedby={anchor ? tooltipId : undefined}
      onMouseEnter={show} onMouseLeave={() => setAnchor(undefined)}
      onFocus={show} onBlur={() => setAnchor(undefined)} onClick={show}>
      <span aria-hidden="true">i</span>
    </button>
    {anchor && <div id={tooltipId} role="tooltip" popover="manual" className="feature-tooltip"
      ref={element => { if (element && !element.matches(":popover-open")) element.showPopover(); }} style={{
        left: Math.min(Math.max(8, anchor.left), Math.max(8, window.innerWidth - 288)),
        ...(anchor.bottom + 120 > window.innerHeight
          ? { bottom: window.innerHeight - anchor.top + 6 }
          : { top: anchor.bottom + 6 }),
      }}>{explanation}</div>}
  </>;
}
