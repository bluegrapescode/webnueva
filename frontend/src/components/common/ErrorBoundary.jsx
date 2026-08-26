import React from "react";
import { AlertTriangle } from "lucide-react";

export class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null, resetKey: props.resetKey };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  static getDerivedStateFromProps(props, state) {
    if (props.resetKey !== state.resetKey) {
      return { hasError: false, error: null, resetKey: props.resetKey };
    }
    return null;
  }

  componentDidCatch(error, info) {
    console.error("[ErrorBoundary] UI crash:", error, info?.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div data-testid="error-boundary" className="min-h-[60vh] flex items-center justify-center px-6">
          <div className="max-w-md w-full glass rounded-2xl border border-crimson/30 p-8 text-center">
            <div className="mx-auto mb-4 w-14 h-14 rounded-2xl bg-crimson/15 border border-crimson/30 flex items-center justify-center">
              <AlertTriangle className="text-crimson" size={26} />
            </div>
            <h2 className="font-display font-extrabold text-2xl mb-2">Algo salió mal</h2>
            <p className="text-sm text-muted-foreground mb-5">
              Ocurrió un error al mostrar esta sección. Puedes recargar la página o volver al inicio; tu progreso está a salvo.
            </p>
            {this.state.error?.message && (
              <pre data-testid="error-message" className="text-[11px] text-left text-crimson/80 bg-black/30 rounded-lg p-3 mb-5 overflow-auto max-h-32">
                {String(this.state.error.message)}
              </pre>
            )}
            <div className="flex gap-3 justify-center">
              <button data-testid="error-reload-btn" onClick={() => window.location.reload()}
                className="px-4 py-2.5 rounded-xl bg-gold text-background font-bold text-sm hover:brightness-110 transition-all">
                Recargar
              </button>
              <button data-testid="error-home-btn" onClick={() => { window.location.href = "/"; }}
                className="px-4 py-2.5 rounded-xl glass border border-white/10 text-sm font-semibold text-muted-foreground hover:text-foreground transition-all">
                Ir al inicio
              </button>
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
