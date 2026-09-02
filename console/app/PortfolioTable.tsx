"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import type { AccountSummary } from "@/lib/api";

const BAND_COLOR: Record<string, string> = {
  healthy: "bg-green-100 text-green-800",
  watch: "bg-yellow-100 text-yellow-800",
  at_risk: "bg-orange-100 text-orange-800",
  critical: "bg-red-100 text-red-800",
};

type SortKey = "name" | "tier" | "band" | "score";

export default function PortfolioTable({ accounts }: { accounts: AccountSummary[] }) {
  const [filter, setFilter] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("score");
  const [sortAsc, setSortAsc] = useState(false);

  const rows = useMemo(() => {
    const needle = filter.toLowerCase();
    const filtered = accounts.filter(
      (a) =>
        a.name.toLowerCase().includes(needle) ||
        a.tier.toLowerCase().includes(needle) ||
        (a.latest_score?.band ?? "").includes(needle)
    );
    const sorted = [...filtered].sort((a, b) => {
      const value = (row: AccountSummary): string | number => {
        switch (sortKey) {
          case "name":
            return row.name;
          case "tier":
            return row.tier;
          case "band":
            return row.latest_score?.band ?? "";
          case "score":
            return row.latest_score?.final_score ?? -1;
        }
      };
      const av = value(a);
      const bv = value(b);
      if (av < bv) return sortAsc ? -1 : 1;
      if (av > bv) return sortAsc ? 1 : -1;
      return 0;
    });
    return sorted;
  }, [accounts, filter, sortKey, sortAsc]);

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortAsc(!sortAsc);
    } else {
      setSortKey(key);
      setSortAsc(true);
    }
  }

  return (
    <div>
      <input
        type="text"
        placeholder="Filter by name, tier, or band..."
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        className="mb-4 w-full max-w-sm rounded border px-3 py-2 text-sm"
      />
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b text-left">
            <th className="cursor-pointer py-2" onClick={() => toggleSort("name")}>
              Account
            </th>
            <th className="cursor-pointer py-2" onClick={() => toggleSort("tier")}>
              Tier
            </th>
            <th className="py-2">Quadrant</th>
            <th className="cursor-pointer py-2" onClick={() => toggleSort("band")}>
              Band
            </th>
            <th className="cursor-pointer py-2" onClick={() => toggleSort("score")}>
              Score
            </th>
            <th className="py-2">Trend</th>
            <th className="py-2">Next review</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((a) => {
            const band = a.latest_score?.band;
            return (
              <tr key={a.account_id} className="border-b hover:bg-gray-50">
                <td className="py-2">
                  <Link href={`/accounts/${a.account_id}`} className="text-blue-700 hover:underline">
                    {a.name}
                  </Link>
                </td>
                <td className="py-2">{a.tier}</td>
                <td className="py-2">{a.quadrant}</td>
                <td className="py-2">
                  {band ? (
                    <span className={`rounded px-2 py-0.5 text-xs font-medium ${BAND_COLOR[band] ?? ""}`}>
                      {band.replace("_", " ")}
                    </span>
                  ) : (
                    <span className="text-gray-400">no score</span>
                  )}
                </td>
                <td className="py-2">{a.latest_score?.final_score?.toFixed(1) ?? "—"}</td>
                <td className="py-2">
                  {a.trend === "up" ? "↑" : a.trend === "down" ? "↓" : a.trend === "flat" ? "→" : "—"}
                </td>
                <td className="py-2">{a.next_review_date ?? "—"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
