import "./globals.css";
import type { ReactNode } from "react";

export const metadata = {
  title: "Polst CS Agent Platform",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-gray-50 text-gray-900">
        <div className="mx-auto max-w-6xl p-6">
          <header className="mb-6 border-b pb-4">
            <a href="/" className="text-lg font-semibold">
              Polst CS
            </a>
          </header>
          {children}
        </div>
      </body>
    </html>
  );
}
