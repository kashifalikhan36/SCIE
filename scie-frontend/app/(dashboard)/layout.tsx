import { Sidebar } from "@/components/layout/sidebar";
import { TopNav } from "@/components/layout/top-nav";

export default function DashboardLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <div className="flex min-h-screen">
      <Sidebar />
      {/* On mobile the sidebar renders as a fixed overlay, so we add top padding to push content below the mobile nav bar */}
      <div className="flex-1 flex flex-col min-w-0 md:pt-0 pt-14">
        <TopNav />
        <main className="flex-1 p-4 md:p-6 overflow-x-hidden">
          {children}
        </main>
      </div>
    </div>
  );
}
