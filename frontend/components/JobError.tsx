import { jobErrorText, type Job } from "@/lib/api";

/** Red notice box that shows a failed job's friendly error. Renders nothing unless the job failed. */
export function JobError({ job, title }: { job: Job | null | undefined; title?: string }) {
  if (!job || job.status !== "failed") return null;
  return (
    <div
      role="alert"
      style={{
        marginTop: 10,
        padding: "10px 12px",
        borderRadius: 8,
        border: "1px solid rgba(248,113,113,.4)",
        background: "rgba(248,113,113,.08)",
      }}
    >
      <strong style={{ color: "var(--err)" }}>⚠️ {title || "Something failed"}</strong>
      <div style={{ marginTop: 4 }}>{jobErrorText(job)}</div>
    </div>
  );
}
