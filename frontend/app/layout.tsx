import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/components/auth/auth-provider";

export const metadata: Metadata = {
  title: "AI Travel Assistant | 智能旅行规划",
  description: "你的智能旅行规划助手，随时为你提供个性化旅行建议，让每一次出发都充满期待",
  icons: {
    icon: "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>✈</text></svg>",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <body className="bg-atmosphere antialiased">
        <AuthProvider>{children}</AuthProvider>

        {/* Deerflow Branding */}
        <div className="deerflow-branding">
          <a
            href="https://deerflow.tech"
            target="_blank"
            rel="noopener noreferrer"
            title="Powered by Deerflow"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
              <polyline points="9 22 9 12 15 12 15 22"/>
            </svg>
            Deerflow
          </a>
        </div>
      </body>
    </html>
  );
}
