import Link from "next/link";
import { fetchReports } from "@/lib/api";

function pct(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `${Math.round(value * 100)}%`;
}

function StatCard({
  label,
  value,
  nullReason,
  tone,
}: {
  label: string;
  value: string;
  nullReason?: string | null;
  tone?: "good" | "bad" | "neutral";
}) {
  const toneClass =
    tone === "good" ? "text-green-700" : tone === "bad" ? "text-red-600" : "text-gray-900";
  return (
    <div className="rounded border p-4">
      <div className="text-xs uppercase tracking-wide text-gray-500">{label}</div>
      <div className={`mt-1 text-2xl font-semibold ${toneClass}`}>{value}</div>
      {nullReason && <div className="mt-1 text-xs text-gray-400">{nullReason.replace(/_/g, " ")}</div>}
    </div>
  );
}

export default async function CalibrationPage() {
  const reports = await fetchReports("calibration_input");
  const [latest, ...history] = reports;

  return (
    <main>
      <h1 className="mb-1 text-xl font-semibold">Calibration</h1>
      <p className="mb-6 text-sm text-gray-600">
        Doc 02 §7's quarterly exercise: "did the score move first, or did the outcome surprise
        you?" Hit rate, false alarm rate, and lead time are computed from real health-score and
        campaign history — never estimated. Naming the missing signal behind a surprise stays a
        human judgment call; this page surfaces which events were surprises, not what caused them.
      </p>

      {!latest && (
        <p className="rounded border border-dashed p-4 text-sm text-gray-500">
          No calibration report yet — run <code>python -m agents.jobs.run_portfolio_analyst</code>{" "}
          against a portfolio with enough health-score history to detect a decay/churn/expansion
          event.
        </p>
      )}

      {latest && (
        <>
          <div className="mb-2 text-xs text-gray-500">
            Period {latest.period_start} → {latest.period_end} · generated{" "}
            {new Date(latest.generated_at).toLocaleString()}
          </div>

          <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
            <StatCard
              label="Hit rate"
              value={pct(latest.data.hit_rate)}
              nullReason={latest.data.hit_rate_null_reason}
              tone={
                latest.data.hit_rate === null
                  ? "neutral"
                  : latest.data.hit_rate >= 0.7
                    ? "good"
                    : "bad"
              }
            />
            <StatCard
              label="False alarm rate"
              value={pct(latest.data.false_alarm_rate)}
              nullReason={latest.data.false_alarm_rate_null_reason}
              tone={
                latest.data.false_alarm_rate === null
                  ? "neutral"
                  : latest.data.false_alarm_rate <= 0.3
                    ? "good"
                    : "bad"
              }
            />
            <StatCard
              label="Median lead time"
              value={
                latest.data.lead_time_days === null
                  ? "—"
                  : `${latest.data.lead_time_days} days`
              }
              nullReason={latest.data.lead_time_null_reason}
            />
          </div>

          {latest.narrative && (
            <p className="mb-6 rounded border-l-4 border-gray-300 bg-gray-50 p-3 text-sm text-gray-700">
              {latest.narrative}
            </p>
          )}

          <h2 className="mb-2 text-sm font-semibold">
            Surprises ({latest.data.surprises?.length ?? 0})
          </h2>
          <p className="mb-2 text-xs text-gray-500">
            Decay/churn events the model did not flag At-risk/Critical a quarter ahead. Name the
            missing signal for each in the next calibration review — this table doesn't guess one.
          </p>
          <table className="mb-8 w-full border-collapse text-sm">
            <thead>
              <tr className="border-b text-left">
                <th className="py-2">Account</th>
                <th className="py-2">Event</th>
                <th className="py-2">Date</th>
                <th className="py-2">Band, 1 quarter before</th>
                <th className="py-2">Band, 2 quarters before</th>
              </tr>
            </thead>
            <tbody>
              {(latest.data.surprises ?? []).map((s: any, i: number) => (
                <tr key={i} className="border-b hover:bg-gray-50">
                  <td className="py-2">
                    {s.account_id ? (
                      <Link href={`/accounts/${s.account_id}`} className="text-blue-700 hover:underline">
                        {s.account_name ?? s.account_id}
                      </Link>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="py-2">{s.event_type}</td>
                  <td className="py-2 text-xs text-gray-600">{s.event_date}</td>
                  <td className="py-2 text-xs text-gray-600">{s.band_one_quarter_before ?? "no score"}</td>
                  <td className="py-2 text-xs text-gray-600">{s.band_two_quarters_before ?? "no score"}</td>
                </tr>
              ))}
              {(!latest.data.surprises || latest.data.surprises.length === 0) && (
                <tr>
                  <td colSpan={5} className="py-4 text-gray-400">
                    No surprises this period.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </>
      )}

      {history.length > 0 && (
        <>
          <h2 className="mb-2 text-sm font-semibold">Prior quarters</h2>
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b text-left">
                <th className="py-2">Period</th>
                <th className="py-2">Hit rate</th>
                <th className="py-2">False alarm rate</th>
                <th className="py-2">Lead time</th>
                <th className="py-2">Events</th>
              </tr>
            </thead>
            <tbody>
              {history.map((r) => (
                <tr key={r.id} className="border-b hover:bg-gray-50">
                  <td className="py-2 text-xs text-gray-600">
                    {r.period_start} → {r.period_end}
                  </td>
                  <td className="py-2">{pct(r.data.hit_rate)}</td>
                  <td className="py-2">{pct(r.data.false_alarm_rate)}</td>
                  <td className="py-2">
                    {r.data.lead_time_days === null ? "—" : `${r.data.lead_time_days}d`}
                  </td>
                  <td className="py-2">{r.data.event_count ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </main>
  );
}
