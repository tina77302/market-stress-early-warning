import './globals.css';
import React from 'react';
import MarketHeader from './MarketHeader';

export const metadata = {
  title: 'Market Risk Intelligence | AI Early Warning System',
  description: 'AI-based U.S. and Korea financial market stress early warning dashboard',
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
        <MarketHeader />

        {/* Main Content */}
        <main className="flex-1 p-6 max-w-[1600px] w-full mx-auto">
          {children}
        </main>
      </body>
    </html>
  );
}
