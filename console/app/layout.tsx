import "./globals.css";
import Link from "next/link";
import type { ReactNode } from "react";

export const metadata = {
  title: "Polst CS Agent Platform",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-gray-50 text-gray-900">
        <div className="mx-auto max-w-6xl p-6">
          <header className="mb-6 flex items-center gap-6 border-b pb-4">
            <Link href="/" className="text-lg font-semibold">
              Polst CS
            </Link>
            <nav className="flex gap-4 text-sm text-gray-600">
              <Link href="/" className="hover:text-gray-900">
                Portfolio
              </Link>
              <Link href="/signals" className="hover:text-gray-900">
                Signals
              </Link>
              <Link href="/queue" className="hover:text-gray-900">
                Approval Queue
              </Link>
            </nav>
          </header>
          {children}
        </div>
      </body>
    </html>
  );
}
