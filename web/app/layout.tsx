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
  metadataBase: new URL(process.env.SITE_URL || "http://localhost:3000"),
  title: "RootSignal — Evidence-backed incident investigation",
  description: "Train, serve, and evaluate tool-using LLM agents on reproducible production incidents.",
  openGraph: {
    title: "RootSignal",
    description: "Find the cause. Show the evidence.",
    images: [{ url: "/og.png", width: 1536, height: 905, alt: "RootSignal — Find the cause. Show the evidence." }],
  },
  twitter: {
    card: "summary_large_image",
    title: "RootSignal",
    description: "Find the cause. Show the evidence.",
    images: ["/og.png"],
  },
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${geistSans.variable} ${geistMono.variable}`}>
        {children}
      </body>
    </html>
  );
}
