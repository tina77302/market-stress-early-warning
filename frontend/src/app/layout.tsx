import './globals.css';
import React from 'react';
import MarketHeader from './MarketHeader';
import { cookies } from 'next/headers';
import { I18nProvider } from './i18n/provider';
import { languageCookie, translateText } from './i18n/messages';

export async function generateMetadata() {
  const language = (await cookies()).get(languageCookie)?.value === 'ko' ? 'ko' : 'en';
  return {
    title: `${translateText(language, 'Market Risk Intelligence')} | ${translateText(language, 'AI EARLY WARNING SYSTEM')}`,
    description: translateText(language, 'AI-based U.S. and Korea financial market stress early warning dashboard'),
  };
}

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const language = (await cookies()).get(languageCookie)?.value === 'ko' ? 'ko' : 'en';
  return (
    <html lang={language} className="dark">
      <body className="bg-dark-bg text-gray-100 min-h-screen flex flex-col antialiased">
        <I18nProvider initialLanguage={language}>
        {/* Navigation Header */}
        <MarketHeader />

        {/* Main Content */}
        <main className="flex-1 p-6 max-w-[1600px] w-full mx-auto">
          {children}
        </main>
        </I18nProvider>
      </body>
    </html>
  );
}
