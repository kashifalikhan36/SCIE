import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Sherlock AI — Ingestion Console",
  description: "SCIE Chrome Extension",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} dark`}
    >
      {/*
        Chrome extension popups get their size from the content.
        We set a fixed width here so the popup never shrinks below 380px,
        and let the height grow naturally with content.
      */}
      <body
        style={{ width: "390px", margin: 0, padding: 0 }}
        className="bg-background text-foreground antialiased overflow-x-hidden"
      >
        {children}
      </body>
    </html>
  );
}
