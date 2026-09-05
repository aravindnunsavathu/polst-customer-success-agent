import Link from "next/link";
import { fetchSignals } from "@/lib/api";

function slaLabel(slaDueAt: string | null): { label: string; overdue: boolean } {
  if (!slaDueAt) return { label: "—", overdue: false };
  const due = new Date(slaDueAt).getTime();
  const now = Date.now();
  const days = Math.round((due - now) / (1000 * 60 * 60 * 24));
  if (days < 0) return { label: `${Math.abs(days)}d overdue`, overdue: true };
  if (days === 0) return { label: "due today", overdue: true };
  return { label: `${days}d left`, overdue: false };
}

export default async function SignalsPage() {
  const signals = await fetchSignals();

  return (
    <main>
      <h1 className="mb-1 text-xl font-semibold">Open Signals</h1>
      <p className="mb-4 text-sm text-gray-600">
        Sorted by priority (tier × open signal count × a rough revenue-at-risk proxy).
      </p>
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b text-left">
            <th className="py-2">Account</th>
            <th className="py-2">Type</th>
            <th className="py-2">Reason</th>
            <th className="py-2">Severity</th>
            <th className="py-2">SLA</th>
          </tr>
        </thead>
        <tbody>
          {signals.map((s) => {
            const sla = slaLabel(s.sla_due_at);
            return (
              <tr key={s.id} className="border-b hover:bg-gray-50">
                <td className="py-2">
                  <Link href={`/accounts/${s.account_id}`} className="text-blue-700 hover:underline">
                    {s.account_name}
                  </Link>
                </td>
                <td className="py-2">{s.type.replace(/_/g, " ")}</td>
                <td className="py-2 text-xs text-gray-600">{s.reason}</td>
                <td className="py-2">{s.severity}</td>
                <td className={`py-2 ${sla.overdue ? "font-medium text-red-600" : ""}`}>{sla.label}</td>
              </tr>
            );
          })}
          {signals.length === 0 && (
            <tr>
              <td colSpan={5} className="py-4 text-gray-400">
                No open signals.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </main>
  );
}
