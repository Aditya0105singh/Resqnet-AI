import { Component, type ErrorInfo, type ReactNode } from "react";

/** A crash in any page shows what happened and how to recover, instead of a blank screen. */
export class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("RESQNET page crashed:", error, info.componentStack);
  }
  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    return (
      <div className="mx-auto max-w-xl p-8">
        <div className="panel p-6">
          <h1 className="font-display text-xl font-semibold">Something went wrong on this page</h1>
          <p className="mt-2 text-sm text-ink-2">The rest of the app is fine. Reload the page, or go back to the home page. If it keeps happening, send this message to the team:</p>
          <pre className="mt-3 max-h-48 overflow-auto rounded-lg bg-wash p-3 text-[12px] whitespace-pre-wrap text-crit">{String(error.stack || error.message).slice(0, 1200)}</pre>
          <div className="mt-4 flex gap-2">
            <button type="button" className="h-9 rounded-lg bg-brand px-4 text-sm font-medium text-white" onClick={() => location.reload()}>
              Reload
            </button>
            <a href="/" className="inline-flex h-9 items-center rounded-lg border border-line-2 px-4 text-sm font-medium">
              Home
            </a>
          </div>
        </div>
      </div>
    );
  }
}
