import { ArrowLeft, Eye, EyeOff, Mic } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, Navigate, useLocation } from "react-router-dom";
import { Button, Card, ErrorBanner, FieldLabel, Input } from "../components/ui";
import { ApiError } from "../lib/api";
import { useAuth } from "../lib/auth";

const DEFAULT_PAGE = "/live";

export function Login() {
  const { status, loginConfigured, login, recheck } = useAuth();
  const location = useLocation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Only ever a path inside this app, because it comes from the router and not from the URL.
  const from = (location.state as { from?: { pathname: string; search: string } } | null)?.from;
  if (status === "in") return <Navigate to={from ? `${from.pathname}${from.search}` : DEFAULT_PAGE} replace />;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(username.trim(), password);
    } catch (err) {
      setPassword("");
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
      void recheck();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-full flex-col items-center justify-center px-4 py-10">
      <div className="ambient" aria-hidden>
        <div className="ambient-grid" />
      </div>
      <main className="relative w-full max-w-sm">
        <div className="mb-6 flex flex-col items-center text-center">
          <div className="grid h-12 w-12 place-items-center rounded-2xl border border-accent/25 bg-accent/10">
            <Mic className="h-5 w-5 text-accent" aria-hidden />
          </div>
          <h1 className="mt-4 text-xl font-semibold tracking-tight text-ink">Log in to Aapda Awaaz</h1>
          <p className="mt-1 text-sm text-ink-3">For dispatchers and administrators</p>
        </div>

        <Card className="p-5">
          {status === "unreachable" ? (
            <div className="space-y-3">
              <ErrorBanner message="The server isn't responding, so you can't log in right now. Check that the backend is running." />
              <Button className="w-full justify-center" onClick={() => void recheck()}>
                Try again
              </Button>
            </div>
          ) : !loginConfigured ? (
            <div className="space-y-2 text-sm text-ink-2" role="status">
              <p className="font-medium text-ink">Login isn't set up yet</p>
              <p>
                Add <code className="rounded bg-surface-3 px-1 font-mono text-xs">ADMIN_PASSWORD</code> to the{" "}
                <code className="rounded bg-surface-3 px-1 font-mono text-xs">.env</code> file, then restart the backend.
              </p>
            </div>
          ) : (
            <form onSubmit={(e) => void submit(e)} className="space-y-4">
              <div>
                <FieldLabel htmlFor="username">Username</FieldLabel>
                <Input
                  id="username"
                  name="username"
                  autoComplete="username"
                  autoFocus
                  required
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                />
              </div>
              <div>
                <FieldLabel htmlFor="password">Password</FieldLabel>
                <div className="relative">
                  <Input
                    id="password"
                    name="password"
                    type={showPassword ? "text" : "password"}
                    autoComplete="current-password"
                    required
                    className="pr-10"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((v) => !v)}
                    aria-label={showPassword ? "Hide password" : "Show password"}
                    aria-pressed={showPassword}
                    className="absolute inset-y-0 right-0 grid w-10 place-items-center rounded-r-md text-ink-3 hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
                  >
                    {showPassword ? <EyeOff className="h-4 w-4" aria-hidden /> : <Eye className="h-4 w-4" aria-hidden />}
                  </button>
                </div>
              </div>
              {error && <ErrorBanner message={error} />}
              <Button type="submit" variant="primary" busy={busy} disabled={!username.trim() || !password} className="w-full justify-center">
                Log in
              </Button>
            </form>
          )}
        </Card>

        <Link to="/" className="mt-5 flex items-center justify-center gap-1.5 text-xs text-ink-3 hover:text-ink">
          <ArrowLeft className="h-3.5 w-3.5" aria-hidden /> Back to home
        </Link>
      </main>
    </div>
  );
}
