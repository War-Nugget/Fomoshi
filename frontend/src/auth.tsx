import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, getToken, setToken, type User } from "./api";

interface AuthState {
  user: User | null;
  loading: boolean;
  signIn: (usernameOrEmail: string, password: string) => Promise<void>;
  signUp: (username: string, email: string, password: string) => Promise<void>;
  /** Store a token from reset/change-password and load the user. */
  startSession: (token: string) => Promise<void>;
  signOut: () => void;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(Boolean(getToken()));

  const refresh = useCallback(async () => {
    if (!getToken()) {
      setUser(null);
      return;
    }
    try {
      setUser(await api.me());
    } catch {
      setUser(null);
    }
  }, []);

  useEffect(() => {
    refresh().finally(() => setLoading(false));
    const onSignedOut = () => setUser(null);
    window.addEventListener("fomoshi:signed-out", onSignedOut);
    return () => window.removeEventListener("fomoshi:signed-out", onSignedOut);
  }, [refresh]);

  const startSession = async (token: string) => {
    setToken(token);
    await refresh();
  };

  const value: AuthState = {
    user,
    loading,
    refresh,
    startSession,
    signIn: async (u, p) => startSession((await api.login(u, p)).access_token),
    signUp: async (u, e, p) => startSession((await api.register(u, e, p)).access_token),
    signOut: () => {
      setToken(null);
      setUser(null);
    },
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
