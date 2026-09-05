import { fetchActions } from "@/lib/api";
import QueueList from "./QueueList";

export default async function ApprovalQueuePage() {
  const actions = await fetchActions("pending");

  return (
    <main>
      <h1 className="mb-1 text-xl font-semibold">Approval Queue</h1>
      <p className="mb-4 text-sm text-gray-600">
        Nothing here yet drafts customer-facing copy — no agent exists before Phase 4. This is
        the operating surface those drafts will land in: approve, or reject with a mandatory
        structured reason (rejection reasons are training data).
      </p>
      <QueueList initialActions={actions} />
    </main>
  );
}
