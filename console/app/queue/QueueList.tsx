"use client";

import { useState } from "react";
import type { ActionOut } from "@/lib/api";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const REJECTION_CATEGORIES = [
  "wrong_cause",
  "wrong_tone",
  "wrong_recipient",
  "factually_incorrect",
  "volume_pushing",
  "premature",
  "other",
];

export default function QueueList({ initialActions }: { initialActions: ActionOut[] }) {
  const [actions, setActions] = useState(initialActions);
  const [approver, setApprover] = useState("");
  const [rejectingId, setRejectingId] = useState<string | null>(null);
  const [category, setCategory] = useState(REJECTION_CATEGORIES[0]);
  const [detail, setDetail] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function approve(id: string) {
    if (!approver.trim()) {
      setError("Enter who's approving this first.");
      return;
    }
    setError(null);
    const res = await fetch(`${API_URL}/actions/${id}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ approved_by: approver }),
    });
    if (!res.ok) {
      setError(`Approve failed: ${res.status}`);
      return;
    }
    setActions((prev) => prev.filter((a) => a.id !== id));
  }

  async function reject(id: string) {
    setError(null);
    const res = await fetch(`${API_URL}/actions/${id}/reject`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rejection_reason_category: category, rejection_reason_detail: detail || null }),
    });
    if (!res.ok) {
      setError(`Reject failed: ${res.status}`);
      return;
    }
    setActions((prev) => prev.filter((a) => a.id !== id));
    setRejectingId(null);
    setDetail("");
  }

  return (
    <div>
      <div className="mb-4">
        <label className="text-sm text-gray-600">Approving as: </label>
        <input
          type="text"
          value={approver}
          onChange={(e) => setApprover(e.target.value)}
          placeholder="your name"
          className="ml-1 rounded border px-2 py-1 text-sm"
        />
      </div>
      {error && <p className="mb-4 text-sm text-red-600">{error}</p>}

      <div className="space-y-4">
        {actions.map((action) => (
          <div key={action.id} className="rounded border p-4">
            <div className="mb-2 flex items-center justify-between">
              <span className="font-medium">{action.type.replace(/_/g, " ")}</span>
              <span className="text-xs text-gray-500">{action.autonomy_level}</span>
            </div>
            <p className="mb-2 text-sm text-gray-700">{action.reasoning}</p>
            <pre className="mb-3 overflow-x-auto rounded bg-gray-50 p-2 text-xs">
              {JSON.stringify(action.payload, null, 2)}
            </pre>

            {rejectingId === action.id ? (
              <div className="space-y-2">
                <select
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  className="rounded border px-2 py-1 text-sm"
                >
                  {REJECTION_CATEGORIES.map((c) => (
                    <option key={c} value={c}>
                      {c.replace(/_/g, " ")}
                    </option>
                  ))}
                </select>
                <textarea
                  value={detail}
                  onChange={(e) => setDetail(e.target.value)}
                  placeholder="Optional detail"
                  className="block w-full rounded border px-2 py-1 text-sm"
                  rows={2}
                />
                <div className="space-x-2">
                  <button
                    onClick={() => reject(action.id)}
                    className="rounded bg-red-600 px-3 py-1 text-sm text-white hover:bg-red-700"
                  >
                    Confirm reject
                  </button>
                  <button onClick={() => setRejectingId(null)} className="text-sm text-gray-600">
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <div className="space-x-2">
                <button
                  onClick={() => approve(action.id)}
                  className="rounded bg-green-600 px-3 py-1 text-sm text-white hover:bg-green-700"
                >
                  Approve
                </button>
                <button
                  onClick={() => setRejectingId(action.id)}
                  className="rounded bg-gray-200 px-3 py-1 text-sm hover:bg-gray-300"
                >
                  Reject
                </button>
              </div>
            )}
          </div>
        ))}
        {actions.length === 0 && <p className="text-gray-400">Nothing pending.</p>}
      </div>
    </div>
  );
}
