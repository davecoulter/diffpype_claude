import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { createDummyJob, getDummyJobStatus, getStatuses } from "../api";

const TERMINAL = new Set(["complete", "failed"]);

export default function DashboardPage() {
  const [imageId, setImageId] = useState<number | null>(null);

  const { data: statusMeta = [] } = useQuery({
    queryKey: ["meta/statuses"],
    queryFn: getStatuses,
  });

  const colorMap = Object.fromEntries(statusMeta.map((s) => [s.value, s.color]));

  const { data: jobStatus, error } = useQuery({
    queryKey: ["jobs/dummy", imageId],
    queryFn: () => getDummyJobStatus(imageId!),
    enabled: imageId !== null,
    refetchInterval: (query) =>
      TERMINAL.has(query.state.data?.status ?? "") ? false : 1000,
  });

  const { mutate: runJob, isPending } = useMutation({
    mutationFn: createDummyJob,
    onSuccess: ({ image_id }) => setImageId(image_id),
  });

  const status = jobStatus?.status ?? "idle";

  return (
    <main style={{ fontFamily: "sans-serif", padding: "2rem" }}>
      <h1>Diffpype — Dashboard</h1>
      <button onClick={() => runJob()} disabled={isPending}>
        {isPending ? "Dispatching…" : "Run Dummy Job"}
      </button>
      <p>
        <span
          style={{
            display: "inline-block",
            width: "0.9rem",
            height: "0.9rem",
            borderRadius: "50%",
            backgroundColor: colorMap[status] ?? "#9e9e9e",
            marginRight: "0.5rem",
            verticalAlign: "middle",
          }}
        />
        {status}
        {imageId !== null && ` (image #${imageId})`}
      </p>
      {error && (
        <p style={{ color: "#c62828" }}>Error: {(error as Error).message}</p>
      )}
    </main>
  );
}
