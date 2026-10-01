import './globals.css';
import React from 'react';
import Link from 'next/link';
import { ShieldAlert, BarChart3, Activity } from 'lucide-react';

export const metadata = {
  title: 'Market Risk Intelligence - U.S. Stress Early Warning',
  description: 'AI-Based U.S. Financial Market Stress Early Warning Dashboard',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ko" className="dark">
      <body className="bg-dark-bg text-gray-100 min-h-screen flex flex-col font-mono antialiased">
        {/* Navigation Header */}
        <header className="border-b border-dark-border bg-dark-card/80 backdrop-blur sticky top-0 z-50 px-6 py-3 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <ShieldAlert className="w-6 h-6 text-financial-red animate-pulse" />
            <span className="font-bold text-lg tracking-wider text-white">
              U.S. MARKET RISK INTELLIGENCE
            </span>
            <span className="text-xs px-2 py-0.5 rounded bg-dark-border text-gray-400">
              AI EARLY WARNING SYSTEM
            </span>
          </div>

          <nav className="flex items-center space-x-6 text-sm font-medium">
            <Link
              href="/"
              className="flex items-center space-x-2 text-gray-300 hover:text-white transition-colors"
            >
              <Activity className="w-4 h-4 text-financial-blue" />
              <span>PAGE 01 — Market Risk</span>
            </Link>
            <Link
              href="/validation"
              className="flex items-center space-x-2 text-gray-300 hover:text-white transition-colors"
            >
              <BarChart3 className="w-4 h-4 text-financial-green" />
              <span>PAGE 02 — Model Validation</span>
            </Link>
          </nav>
        </header>

        {/* Main Content */}
        <main className="flex-1 p-6 max-w-[1600px] w-full mx-auto">
          {children}
        </main>
      </body>
    </html>
  );
}
