import Link from "next/link";
import { fetchPlays } from "@/lib/api";

const PLAY_TYPES = ["onboarding", "decay", "renewal", "expansion"];

function outcomeClass(outcome: string | null): string {
  if (!outcome) return "text-gray-500";
  if (["completed_successfully", "recommitment_secured", "recovered"].includes(outcome)) {
    return "text-green-700";
  }
  if (["gate_not_met", "handoff_rejected", "lost", "stalled", "no_intervention_seasonal"].includes(outcome)) {
    return "text-gray-500";
  }
  if (outcome.startsWith("stalled") || outcome === "undetermined") return "text-amber-700";
  return "text-gray-700";
}

function FilterLink({
  label,
  href,
  active,
}: {
  label: string;
  href: string;
  active: boolean;
}) {
  return (
    <Link
      href={href}
      className={`rounded px-2 py-1 text-xs ${
        active ? "bg-gray-900 text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"
      }`}
    >
      {label}
    </Link>
  );
}

export default async function PlayLogPage({
  searchParams,
}: {
  searchParams: Promise<{ play?: string; status?: string }>;
}) {
  const { play, status } = await searchParams;
  const plays = await fetchPlays({ play, status });

  return (
    <main>
      <h1 className="mb-1 text-xl font-semibold">Play Log</h1>
      <p className="mb-4 text-sm text-gray-600">
        Every play run, its exit test result, cause classification, and outcome — "a play we
        cannot evaluate is a ritual." This is the raw material doc 06's play backlog turns into an
        actual playbook after two quarters.
      </p>

      <div className="mb-4 flex flex-wrap gap-2">
        <FilterLink label="All statuses" href="/plays" active={!status && !play} />
        <FilterLink label="Open" href="/plays?status=open" active={status === "open"} />
        <FilterLink label="Closed" href="/plays?status=closed" active={status === "closed"} />
        <span className="mx-1 text-gray-300">|</span>
        {PLAY_TYPES.map((p) => (
          <FilterLink key={p} label={p} href={`/plays?play=${p}`} active={play === p} />
        ))}
      </div>

      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b text-left">
            <th className="py-2">Account</th>
            <th className="py-2">Play</th>
            <th className="py-2">Opened</th>
            <th className="py-2">Closed</th>
            <th className="py-2">Outcome</th>
            <th className="py-2">Cause</th>
            <th className="py-2">Actions</th>
          </tr>
        </thead>
        <tbody>
          {plays.map((p) => (
            <tr key={p.id} className="border-b align-top hover:bg-gray-50">
              <td className="py-2">
                <Link href={`/accounts/${p.account_id}`} className="text-blue-700 hover:underline">
                  {p.account_name}
                </Link>
                <div className="text-xs text-gray-400">{p.tier}</div>
              </td>
              <td className="py-2">{p.play}</td>
              <td className="py-2 text-xs text-gray-600">{new Date(p.opened_at).toLocaleDateString()}</td>
              <td className="py-2 text-xs text-gray-600">
                {p.closed_at ? new Date(p.closed_at).toLocaleDateString() : "—"}
              </td>
              <td className={`py-2 text-xs font-medium ${outcomeClass(p.outcome)}`}>
                {p.outcome ? p.outcome.replace(/_/g, " ") : "open"}
              </td>
              <td className="py-2 text-xs text-gray-600">
                {p.cause_classification ? p.cause_classification.replace(/_/g, " ") : "—"}
              </td>
              <td className="py-2">
                <details>
                  <summary className="cursor-pointer text-xs text-blue-700 hover:underline">
                    {p.actions.length} action{p.actions.length === 1 ? "" : "s"}
                  </summary>
                  <div className="mt-2 space-y-2">
                    {p.actions.map((a) => (
                      <div key={a.id} className="rounded border bg-gray-50 p-2 text-xs">
                        <div className="mb-1 flex items-center justify-between gap-2">
                          <span className="font-medium">{a.type.replace(/_/g, " ")}</span>
                          <span className="text-gray-500">
                            {a.autonomy_level} · {a.status}
                          </span>
                        </div>
                        <p className="text-gray-600">{a.reasoning}</p>
                      </div>
                    ))}
                    {Object.keys(p.exit_test_results).length > 0 && (
                      <pre className="overflow-x-auto rounded bg-gray-50 p-2 text-xs">
                        {JSON.stringify(p.exit_test_results, null, 2)}
                      </pre>
                    )}
                  </div>
                </details>
              </td>
            </tr>
          ))}
          {plays.length === 0 && (
            <tr>
              <td colSpan={7} className="py-4 text-gray-400">
                No play runs match this filter.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </main>
  );
}
