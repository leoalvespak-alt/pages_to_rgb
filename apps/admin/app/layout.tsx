import "./globals.css";

export const metadata = { title: "Pages to RGB — Admin", description: "Admin limpo para ptr" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <body className="min-h-screen bg-[#0A0A0A] text-white antialiased">{children}</body>
    </html>
  );
}
