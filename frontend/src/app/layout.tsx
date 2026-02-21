import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Agent Brain — AI IDE Control Panel",
  description: "Local AI-IDE Control Panel with memory, analytics and project context",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-background text-foreground antialiased">
        {children}
      </body>
    </html>
  );
}
