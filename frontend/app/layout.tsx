/* eslint-disable @next/next/no-page-custom-font, @next/next/no-sync-scripts */
import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'BLUE | Water Quality Intelligence by Project BLUE',
  description: 'BLUE is a multi-standard Water Quality Index engine. Analyse drinking water, agriculture, industrial, and aquaculture quality against BIS, WHO, and FAO standards — instantly.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet" />
        <script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js"></script>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/ScrollTrigger.min.js"></script>
      </head>
      <body>
        {children}
      </body>
    </html>
  );
}
