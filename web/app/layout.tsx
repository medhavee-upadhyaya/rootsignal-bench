import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const configuredPath = process.env.ROOTSIGNAL_BASE_PATH?.trim() || "";
const basePath = configuredPath && configuredPath !== "/"
  ? `/${configuredPath.replace(/^\/+|\/+$/g, "")}`
  : "";

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
    images: [{ url: `${basePath}/og.png`, width: 1536, height: 905, alt: "RootSignal — Find the cause. Show the evidence." }],
  },
  twitter: {
    card: "summary_large_image",
    title: "RootSignal",
    description: "Find the cause. Show the evidence.",
    images: [`${basePath}/og.png`],
  },
  icons: {
    icon: `${basePath}/favicon.svg`,
    shortcut: `${basePath}/favicon.svg`,
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
