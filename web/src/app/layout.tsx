import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";

import { AppShell, THEME_SCRIPT } from "@/components/shell";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: { default: "Rafta · Inventory optimisation", template: "%s · Rafta" },
  description:
    "AI inventory optimisation for SMEs: ABC/XYZ classification, backtested demand forecasts, safety stock and reorder points, and ABC-vs-uniform policy simulation.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} antialiased`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
