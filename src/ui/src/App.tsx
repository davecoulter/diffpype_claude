import { useEffect, useRef, useState } from "react";

import { createDummyJob, getDummyJobStatus } from "./api";

const STATUS_COLORS: Record<string, string> = {
  Running: "#e0a800",
  Success: "#2e7d32",
  Failed: "#c62828",
};

const TERMINAL_STATUSES = new Set(["Success", "Failed"]);

export default function App() {
  const [imageId, setImageId] = useState<number | null>(null);
  const [status, setStatus] = useState<string>("Idle");
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (pollRef.current !== null) {
        window.clearInterval(pollRef.current);
      }
    };
  }, []);

  async function handleRunJob() {
    setError(null);
    try {
      const { image_id } = await createDummyJob();
      setImageId(image_id);
      setStatus("Running");

      if (pollRef.current !== null) {
        window.clearInterval(pollRef.current);
      }
      pollRef.current = window.setInterval(async () => {
        try {
          const result = await getDummyJobStatus(image_id);
          setStatus(result.status);
          if (TERMINAL_STATUSES.has(result.status) && pollRef.current !== null) {
            window.clearInterval(pollRef.current);
            pollRef.current = null;
          }
        } catch (err) {
          setError((err as Error).message);
        }
      }, 1000);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <main style={{ fontFamily: "sans-serif", padding: "2rem" }}>
      <h1>Diffpype Walking Skeleton</h1>
      <button onClick={handleRunJob}>Run Dummy Job</button>
      <p>
        Status:{" "}
        <span
          style={{
            display: "inline-block",
            width: "0.9rem",
            height: "0.9rem",
            borderRadius: "50%",
            backgroundColor: STATUS_COLORS[status] ?? "#9e9e9e",
            marginRight: "0.4rem",
          }}
        />
        {status}
        {imageId !== null && ` (image #${imageId})`}
      </p>
      {error && <p style={{ color: "#c62828" }}>Error: {error}</p>}
    </main>
  );
}
