import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "HYDRA | Enterprise Ticket Monitoring",
  description: "The automated inventory system for Vatican Museums. We sniff out availability and snipe tickets instantly.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning style={{ colorScheme: 'dark', backgroundColor: '#050505' }}>
      <head>
        <meta name="color-scheme" content="dark" />
      </head>
      <body className={inter.className} style={{ backgroundColor: '#050505', color: '#ffffff', minHeight: '100vh' }}>
        {children}
      </body>
    </html>
  );
}
