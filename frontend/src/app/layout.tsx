import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "CareerPilot AI",
  description: "Autonomous multi-agent career navigation",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
