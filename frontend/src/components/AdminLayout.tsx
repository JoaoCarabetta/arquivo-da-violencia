import { Link, useLocation, useNavigate } from 'react-router-dom';
import { cn } from '@/lib/utils';
import { useAuth } from '@/contexts/AuthContext';
import { Button } from '@/components/ui/button';
import {
  LayoutDashboard,
  Newspaper,
  FileText,
  CheckCircle,
  Cog,
  ArrowLeft,
  LogOut,
} from 'lucide-react';

const navItems = [
  { path: '/admin', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/admin/sources', label: 'Sources', icon: Newspaper },
  { path: '/admin/raw-events', label: 'Raw Events', icon: FileText },
  { path: '/admin/unique-events', label: 'Unique Events', icon: CheckCircle },
  { path: '/admin/jobs', label: 'Jobs', icon: Cog },
];

function NavLink({
  item,
  isActive,
  compact = false,
}: {
  item: (typeof navItems)[number];
  isActive: boolean;
  compact?: boolean;
}) {
  return (
    <Link
      to={item.path}
      className={cn(
        'flex items-center gap-3 rounded-lg font-medium transition-colors',
        compact
          ? 'min-h-10 shrink-0 gap-2 px-3 py-2 text-xs'
          : 'px-3 py-2 text-sm',
        isActive
          ? 'bg-primary text-primary-foreground'
          : 'text-muted-foreground hover:bg-muted hover:text-foreground'
      )}
    >
      <item.icon className={compact ? 'h-3.5 w-3.5' : 'h-4 w-4'} />
      {item.label}
    </Link>
  );
}

export function AdminLayout({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  const navigate = useNavigate();
  const { logout } = useAuth();

  const handleLogout = () => {
    logout();
    navigate('/admin/login');
  };

  return (
    <div className="min-h-dvh bg-background">
      <aside className="fixed inset-y-0 left-0 z-50 hidden w-64 border-r bg-card md:block">
        <div className="flex h-16 items-center border-b px-6">
          <h1 className="text-lg font-semibold tracking-tight">
            <span className="text-rose-600">Arquivo da Violência</span>
          </h1>
        </div>

        <div className="border-b p-4">
          <Link
            to="/"
            className="flex items-center gap-2 text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            <ArrowLeft className="h-4 w-4" />
            Voltar ao site público
          </Link>
        </div>

        <nav className="flex-1 space-y-1 p-4">
          {navItems.map((item) => (
            <NavLink
              key={item.path}
              item={item}
              isActive={location.pathname === item.path}
            />
          ))}
        </nav>

        <div className="absolute bottom-0 left-0 right-0 border-t bg-card p-4">
          <Button
            variant="ghost"
            className="w-full justify-start text-muted-foreground hover:text-foreground"
            onClick={handleLogout}
          >
            <LogOut className="mr-3 h-4 w-4" />
            Sair
          </Button>
        </div>
      </aside>

      <header className="sticky top-0 z-40 border-b bg-card md:hidden">
        <div className="flex items-center justify-between gap-3 px-4 py-3">
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold text-rose-600">Arquivo da Violência</div>
            <Link
              to="/"
              className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
            >
              <ArrowLeft className="h-3 w-3" />
              Site público
            </Link>
          </div>
          <Button variant="ghost" size="sm" className="min-h-10 shrink-0" onClick={handleLogout}>
            <LogOut className="h-4 w-4" />
            Sair
          </Button>
        </div>
        <nav className="flex gap-1 overflow-x-auto px-3 pb-3">
          {navItems.map((item) => (
            <NavLink
              key={item.path}
              item={item}
              isActive={location.pathname === item.path}
              compact
            />
          ))}
        </nav>
      </header>

      <main className="md:pl-64">
        <div className="container max-w-7xl px-4 py-6 md:px-8 md:py-8">
          {children}
        </div>
      </main>
    </div>
  );
}
