import { Link, useLocation } from 'react-router-dom';
import { cn } from '@/lib/utils';
import { Github } from 'lucide-react';

const navItems = [
  { path: '/', label: 'Início', exact: true },
  { path: '/eventos', label: 'Eventos' },
  { path: '/dados', label: 'Dados' },
  { path: '/sobre', label: 'Sobre' },
];

export function PublicLayout({ children }: { children: React.ReactNode }) {
  const location = useLocation();

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b bg-card sticky top-0 z-50">
        <div className="container mx-auto px-6">
          <div className="flex h-16 items-center justify-between">
            {/* Logo */}
            <Link to="/">
              <h1 className="text-lg font-semibold tracking-tight">
                <span className="text-rose-600">Arquivo da Violência</span>
              </h1>
            </Link>

            {/* Navigation */}
            <nav className="flex items-center gap-1">
              {navItems.map((item) => {
                const isActive = item.exact 
                  ? location.pathname === item.path
                  : location.pathname.startsWith(item.path) && item.path !== '/';
                
                return (
                  <Link
                    key={item.path}
                    to={item.path}
                    className={cn(
                      'px-4 py-2 text-sm font-medium rounded-md transition-colors',
                      isActive
                        ? 'bg-primary text-primary-foreground'
                        : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                    )}
                  >
                    {item.label}
                  </Link>
                );
              })}
              
              {/* Admin link */}
              <Link
                to="/admin"
                className="ml-4 px-3 py-2 text-xs font-medium rounded-md border border-border text-muted-foreground hover:bg-muted transition-colors"
              >
                Admin
              </Link>
            </nav>
          </div>
        </div>
      </header>

      {/* Main content */}
      <main>
        {children}
      </main>

      {/* Footer */}
      <footer className="border-t mt-20 py-8 bg-card">
        <div className="container mx-auto px-6">
          <div className="flex flex-col md:flex-row justify-between items-center gap-4">
            <div className="text-sm text-muted-foreground">
              © 2025 Arquivo da Violência. Dados abertos para pesquisa e jornalismo.
            </div>
            <div className="flex items-center gap-4">
              <div className="flex gap-4 text-sm">
                <Link to="/sobre" className="text-muted-foreground hover:text-foreground">
                  Sobre
                </Link>
                <Link to="/dados" className="text-muted-foreground hover:text-foreground">
                  Dados
                </Link>
                <a
                  href="https://github.com/JoaoCarabetta/arquivo-da-violencia"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-muted-foreground hover:text-foreground"
                >
                  GitHub
                </a>
              </div>
              <a
                href="https://github.com/JoaoCarabetta/arquivo-da-violencia"
                target="_blank"
                rel="noopener noreferrer"
                className="text-muted-foreground hover:text-foreground transition-colors"
                aria-label="GitHub"
              >
                <Github className="h-5 w-5" />
              </a>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}

