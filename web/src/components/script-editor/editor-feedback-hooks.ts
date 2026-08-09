import { useEffect, useRef, useState } from "react";

import { durationStatusLabel, type DurationAssessment } from "@/lib/script-editor";

export function useDurationAnnouncement(assessment: DurationAssessment) {
  const [announcement, setAnnouncement] = useState("");

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      setAnnouncement(`${durationStatusLabel(assessment.status)}. ${assessment.message}`);
    }, 450);
    return () => window.clearTimeout(timeout);
  }, [assessment.message, assessment.status]);

  return announcement;
}

export function useEditorErrorFocus(error: string | null) {
  const errorRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (error) errorRef.current?.focus();
  }, [error]);

  return errorRef;
}
