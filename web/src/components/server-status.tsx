"use client";

import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useSWRConfig } from "swr";

/**
 * The hosted demo runs the API on a free tier that sleeps when idle; the first request
 * can take 30-60 s. If the API is slow to answer, say so instead of looking broken,
 * keep pinging, and refresh every query once it is awake.
 */
export function ServerStatus() {
  const { mutate } = useSWRConfig();
  const [waking, setWaking] = useState(false);
  const [seconds, setSeconds] = useState(0);

  useEffect(() => {
    let cancelled = false;
    let slowTimer: ReturnType<typeof setTimeout> | undefined;
    const started = Date.now();
    const tick = setInterval(() => setSeconds(Math.round((Date.now() - started) / 1000)), 1000);

    const ping = async (): Promise<boolean> => {
      try {
        const res = await fetch("/api/v1/data/status", { cache: "no-store" });
        return res.ok;
      } catch {
        return false;
      }
    };

    (async () => {
      slowTimer = setTimeout(() => !cancelled && setWaking(true), 2500);
      for (let attempt = 0; attempt < 60 && !cancelled; attempt++) {
        if (await ping()) {
          clearTimeout(slowTimer);
          if (!cancelled && attempt > 0) await mutate(() => true);
          if (!cancelled) setWaking(false);
          return;
        }
        setWaking(true);
        await new Promise((r) => setTimeout(r, 4000));
      }
    })();

    return () => {
      cancelled = true;
      clearTimeout(slowTimer);
      clearInterval(tick);
    };
  }, [mutate]);

  if (!waking) return null;
  return (
    <div
      role="status"
      className="mb-6 flex items-center gap-3 rounded-lg border border-border bg-accent-soft px-4 py-3 text-sm text-fg"
    >
      <Loader2 size={16} className="shrink-0 animate-spin text-accent" aria-hidden />
      <span>
        Waking up the demo server ({seconds}s). It runs on a free tier that sleeps when idle, so the first load
        takes up to a minute. Data will appear automatically.
      </span>
    </div>
  );
}
