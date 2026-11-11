import "./style.css";
export const metadata = {
  title: "Mini-Nota · Imaging Analysis",
  description: "Public Lung1 imaging workflow demonstration",
};
export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
