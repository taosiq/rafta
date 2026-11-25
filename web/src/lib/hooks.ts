"use client";

import { useCallback, useState } from "react";
import useSWR, { useSWRConfig, type SWRConfiguration } from "swr";

import { api, fetcher, type Job } from "./api";

export function useApi<T>(path: string | null, config?: SWRConfiguration<T>) {
  // keepPreviousData: refetches keep the frame instead of flashing a skeleton
  return useSWR<T>(path, fetcher, { revalidateOnFocus: false, keepPreviousData: true, ...config });
}

/** Start a background job and poll until it finishes, then revalidate every cached query. */
export function useJobRunner() {
  const { mutate } = useSWRConfig();
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);

  const track = useCallback(
    async (jobId: number) => {
      for (;;) {
        const j = await fetcher<Job>(`/jobs/${jobId}`);
        setJob(j);
        if (j.status === "success" || j.status === "failed") break;
        await new Promise((r) => setTimeout(r, 1500));
      }
      await mutate(() => true);
    },
    [mutate],
  );

  const run = useCallback(
    async (jobType: string) => {
      setError(null);
      try {
        const { job_id } = await api.post<{ job_id: number }>("/jobs", { job_type: jobType });
        await track(job_id);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Job failed");
      }
    },
    [track],
  );

  const seed = useCallback(async () => {
    setError(null);
    try {
      const { job_id } = await api.post<{ job_id: number }>("/demo/seed", {});
      await track(job_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Seeding failed");
    }
  }, [track]);

  const busy = job !== null && (job.status === "queued" || job.status === "running");
  return { job, busy, error, run, seed, track };
}
