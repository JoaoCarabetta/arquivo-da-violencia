import { Link, useLocation } from 'react-router-dom';
import { cn } from '@/lib/utils';
import {
  LayoutDashboard,
  Newspaper,
  FileText,
  CheckCircle,
  Cog,
} from 'lucide-react';

const navItems = [
  { path: '/', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/sources', label: 'Sources', icon: Newspaper },
  { path: '/raw-events', label: 'Raw Events', icon: FileText },
  { path: '/unique-events', label: 'Unique Events', icon: CheckCircle },
  { path: '/jobs', label: 'Jobs', icon: Cog },
];

export function Layout({ children }: { children: React.ReactNode }) {
  const location = useLocation();

  return (
    <div className="min-h-screen bg-background">
      {/* Sidebar */}
      <aside className="fixed inset-y-0 left-0 z-50 w-64 border-r bg-card">
        <div className="flex h-16 items-center border-b px-6">
          <h1 className="text-lg font-semibold tracking-tight">
            <span className="text-rose-600">Arquivo</span> da Violência
          </h1>
        </div>
        <nav className="space-y-1 p-4">
          {navItems.map((item) => {
            const isActive = location.pathname === item.path;
            return (
              <Link
                key={item.path}
                to={item.path}
                className={cn(
                  'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                )}
              >
                <item.icon className="h-4 w-4" />
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="absolute bottom-4 left-4 right-4">
          <div className="rounded-lg bg-muted px-3 py-2 text-xs text-muted-foreground">
            <p className="font-medium">v1 Development</p>
            <p>FastAPI + SQLModel + React</p>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main className="pl-64">
        <div className="container max-w-7xl py-8 px-8">
          {children}
        </div>
      </main>
    </div>
  );
}

