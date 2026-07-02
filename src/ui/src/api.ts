const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export interface JobDispatchResponse {
  job_id: string;
  image_id: number;
}

export interface DummyImageStatus {
  id: number;
  status: string;
  latest_job_id: string | null;
}

export interface StatusMetadata {
  value: string;
  label: string;
  color: string;
}

export async function createDummyJob(): Promise<JobDispatchResponse> {
  const response = await fetch(`${API_URL}/jobs/dummy`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      task_name: "dummy_sleep",
      config: { sleep_duration: 5 },
    }),
  });
  if (!response.ok) throw new Error(`Failed to create dummy job: ${response.status}`);
  return response.json();
}

export async function getDummyJobStatus(imageId: number): Promise<DummyImageStatus> {
  const response = await fetch(`${API_URL}/jobs/dummy/${imageId}`);
  if (!response.ok) throw new Error(`Failed to fetch job status: ${response.status}`);
  return response.json();
}

export async function getStatuses(): Promise<StatusMetadata[]> {
  const response = await fetch(`${API_URL}/meta/statuses`);
  if (!response.ok) throw new Error(`Failed to fetch status metadata: ${response.status}`);
  return response.json();
}
