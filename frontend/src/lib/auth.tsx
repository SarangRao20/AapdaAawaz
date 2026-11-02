import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { Spinner } from "../components/ui";
import { api, UNAUTHORIZED_EVENT, type Session } from "./api";

type Status = "loading" | "in" | "out" | "unreachable";

interface Auth {
  status: Status;
  username: string | null;
  loginConfigured: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  recheck: () => Promise<void>;
}

const AuthContext = createContext<Auth | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status>("loading");
  const [username, setUsername] = useState<string | null>(null);
  const [loginConfigured, setLoginConfigured] = useState(true);

  const apply = useCallback((s: Session) => {
    setUsername(s.username);
    setLoginConfigured(s.login_configured);
    setStatus(s.authenticated ? "in" : "out");
  }, []);

  const recheck = useCallback(async () => {
    try {
      apply(await api.session());
    } catch {
      setStatus("unreachable");
    }
  }, [apply]);

  useEffect(() => {
    void recheck();
    // Any API call refused with 401 means the session has ended, so send the person to the login page.
    const onUnauthorized = () => {
      setUsername(null);
      setStatus("out");
    };
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, [recheck]);

  const value = useMemo<Auth>(
    () => ({
      status,
      username,
      loginConfigured,
      recheck,
      login: async (name, password) => apply(await api.login(name, password)),
      logout: async () => {
        // Leave the dashboard even if the request fails; the cookie expires by itself.
        try {
          apply(await api.logout());
        } catch {
          setUsername(null);
          setStatus("out");
        }
      },
    }),
    [status, username, loginConfigured, recheck, apply],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): Auth {
  const auth = useContext(AuthContext);
  if (!auth) throw new Error("useAuth must be used inside AuthProvider");
  return auth;
}

/** Shows children only to a logged-in person. The API enforces this too; this only decides what to display. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  const location = useLocation();
  if (status === "loading") {
    return (
      <div className="grid min-h-full place-items-center">
        <Spinner label="Checking your session…" />
      </div>
    );
  }
  if (status !== "in") return <Navigate to="/login" replace state={{ from: location }} />;
  return <>{children}</>;
}
