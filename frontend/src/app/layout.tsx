import type { Metadata } from "next";
import { Inter, Sora, Lora } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/lib/auth";
import { Toaster } from "@/components/ui/sonner";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

const sora = Sora({
  subsets: ["latin"],
  variable: "--font-heading",
  display: "swap",
  weight: ["500", "600", "700"],
});

const lora = Lora({
  subsets: ["latin"],
  variable: "--font-reading",
  display: "swap",
});

export const metadata: Metadata = {
  title: "SEO SaaS IA",
  description: "Ferramentas de SEO com inteligência artificial para otimização de conteúdo",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="pt-BR" className={`${inter.variable} ${sora.variable} ${lora.variable}`}>
      <body className="min-h-full flex flex-col font-sans antialiased">
        <AuthProvider>
          <div className="flex-1">{children}</div>
          <Toaster />
        </AuthProvider>
      </body>
    </html>
  );
}