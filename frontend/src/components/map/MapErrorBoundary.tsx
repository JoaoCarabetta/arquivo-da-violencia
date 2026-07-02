import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export class MapErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Map render error:', error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div
          className="absolute inset-0 flex flex-col items-center justify-center gap-3 px-6 text-center"
          style={{ background: 'var(--stone-100)', color: 'var(--color-text-muted)' }}
        >
          <p className="m-0 max-w-sm text-sm">
            Não foi possível carregar o mapa neste dispositivo. Tente recarregar a página.
          </p>
          <button
            type="button"
            className="rounded-lg px-4 py-2 text-sm font-medium text-white"
            style={{ background: 'var(--blue-500)' }}
            onClick={() => this.setState({ error: null })}
          >
            Tentar novamente
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
