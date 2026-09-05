import Link from "next/link";
import { fetchAccount } from "@/lib/api";

export default async function AccountPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const account = await fetchAccount(id);
  const plan = account.account_plan;

  return (
    <main>
      <Link href="/" className="text-sm text-blue-700 hover:underline">
        ← Portfolio
      </Link>
      <h1 className="mb-1 mt-2 text-xl font-semibold">{account.name}</h1>
      <p className="mb-6 text-sm text-gray-600">
        {account.tier} · {account.quadrant} · {account.commercial_model}
      </p>

      {account.open_signals.length > 0 && (
        <section className="mb-8 rounded border border-red-200 bg-red-50 p-4">
          <h2 className="mb-2 font-semibold text-red-800">
            Open signals ({account.open_signals.length})
          </h2>
          <ul className="space-y-1 text-sm text-red-900">
            {account.open_signals.map((s) => (
              <li key={s.id}>
                <span className="font-medium">{s.type.replace(/_/g, " ")}</span> — {s.reason}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="mb-8 rounded border p-4">
        <h2 className="mb-2 font-semibold">The business result they bought Polst to achieve</h2>
        {plan.stated_objective_missing ? (
          <p className="rounded bg-red-50 px-3 py-2 text-sm text-red-700">
            No stated objective on record — doc 05 §3 calls this the single most important gap
            in the account.
          </p>
        ) : (
          <>
            <p className="text-sm">{plan.stated_objective}</p>
            {plan.how_measured && (
              <p className="mt-1 text-xs text-gray-500">Measured by: {plan.how_measured}</p>
            )}
            {plan.baseline && <p className="text-xs text-gray-500">Baseline: {plan.baseline}</p>}
          </>
        )}
      </section>

      <section className="mb-8 grid grid-cols-2 gap-4">
        <div className="rounded border p-4">
          <h2 className="mb-2 font-semibold">Top risk</h2>
          <p className="text-sm text-gray-700">{plan.top_risk ?? "—"}</p>
        </div>
        <div className="rounded border p-4">
          <h2 className="mb-2 font-semibold">Top opportunity</h2>
          <p className="text-sm text-gray-700">{plan.top_opportunity ?? "—"}</p>
        </div>
      </section>

      <section className="mb-8">
        <h2 className="mb-2 font-semibold">Health history</h2>
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b text-left">
              <th className="py-2">Scored at</th>
              <th className="py-2">Band</th>
              <th className="py-2">Final</th>
              <th className="py-2">Composite</th>
              <th className="py-2">Overrides</th>
              <th className="py-2">Nulls</th>
            </tr>
          </thead>
          <tbody>
            {account.health_history.map((hs) => (
              <tr key={hs.scored_at} className="border-b">
                <td className="py-2">{new Date(hs.scored_at).toLocaleString()}</td>
                <td className="py-2">{hs.band ?? "—"}</td>
                <td className="py-2">{hs.final_score?.toFixed(1) ?? "—"}</td>
                <td className="py-2">{hs.composite_score?.toFixed(1) ?? "—"}</td>
                <td className="py-2 text-xs">{hs.applied_overrides.join(", ") || "—"}</td>
                <td className="py-2 text-xs">{Object.keys(hs.null_reasons).join(", ") || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="mb-8">
        <h2 className="mb-2 font-semibold">Stakeholder map</h2>
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b text-left">
              <th className="py-2">Name</th>
              <th className="py-2">Type</th>
              <th className="py-2">Relationship</th>
              <th className="py-2">Last contact</th>
              <th className="py-2">Reference willing</th>
            </tr>
          </thead>
          <tbody>
            {account.stakeholders.map((s, i) => (
              <tr key={i} className="border-b">
                <td className="py-2">{s.name}</td>
                <td className="py-2">{s.type.replace("_", " ")}</td>
                <td className="py-2">{s.relationship_strength}</td>
                <td className="py-2">
                  {s.last_contact_at ? new Date(s.last_contact_at).toLocaleDateString() : "—"}
                </td>
                <td className="py-2">{s.reference_willing ? "Yes" : "—"}</td>
              </tr>
            ))}
            {account.stakeholders.length === 0 && (
              <tr>
                <td colSpan={5} className="py-2 text-gray-400">
                  No stakeholders mapped
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </section>

      <section className="mb-8">
        <h2 className="mb-2 font-semibold">Campaign volume by department</h2>
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b text-left">
              <th className="py-2">Department</th>
              <th className="py-2">Live (90d)</th>
              <th className="py-2">Active creators</th>
              <th className="py-2">Last 90d</th>
              <th className="py-2">Prior 90d</th>
            </tr>
          </thead>
          <tbody>
            {account.departments.map((d) => (
              <tr key={d.department_id} className="border-b">
                <td className="py-2">{d.name}</td>
                <td className="py-2">{d.live_last_90d ? "Yes" : "No"}</td>
                <td className="py-2">{d.active_creators_last_90d}</td>
                <td className="py-2">{d.campaigns_last_90d}</td>
                <td className="py-2">{d.campaigns_prior_90d}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="mb-8">
        <h2 className="mb-2 font-semibold">Play history</h2>
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b text-left">
              <th className="py-2">Play</th>
              <th className="py-2">Opened</th>
              <th className="py-2">Closed</th>
              <th className="py-2">Outcome</th>
              <th className="py-2">Cause</th>
            </tr>
          </thead>
          <tbody>
            {account.play_runs.map((p) => (
              <tr key={p.id} className="border-b">
                <td className="py-2">{p.play}</td>
                <td className="py-2">{new Date(p.opened_at).toLocaleDateString()}</td>
                <td className="py-2">
                  {p.closed_at ? new Date(p.closed_at).toLocaleDateString() : "open"}
                </td>
                <td className="py-2">{p.outcome ?? "—"}</td>
                <td className="py-2">{p.cause_classification ?? "—"}</td>
              </tr>
            ))}
            {account.play_runs.length === 0 && (
              <tr>
                <td colSpan={5} className="py-2 text-gray-400">
                  No plays run yet
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </section>
    </main>
  );
}
