import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { api } from '../api/client';
import * as authApi from '../api/authApi';
import type { LoginOtpVerifyPayload, LoginPayload, MeResponse, SignupPayload, VerifyOtpPayload } from '../types/auth';

interface AuthContextValue {
  accessToken: string | null;
  user: MeResponse | null;
  loading: boolean;
  signup: (payload: SignupPayload) => Promise<void>;
  verifyOtp: (payload: VerifyOtpPayload) => Promise<void>;
  login: (payload: LoginPayload) => Promise<void>;
  requestLoginOtp: (email: string) => Promise<void>;
  verifyLoginOtp: (payload: LoginOtpVerifyPayload) => Promise<void>;
  logout: () => Promise<void>;
  ensureSession: () => Promise<void>;
  refreshMe: () => Promise<void>;
  startGoogleSSO: () => void;
  startMicrosoftSSO: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export const AuthProvider = ({ children }: { children: React.ReactNode }) => {
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [user, setUser] = useState<MeResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchMe = useCallback(async (token: string) => {
    const me = await authApi.me(token);
    setUser(me);
  }, []);

  const ensureSession = useCallback(async () => {
    try {
      const token = await authApi.refresh();
      setAccessToken(token.access_token);
      await fetchMe(token.access_token);
    } catch {
      setAccessToken(null);
      setUser(null);
    }
  }, [fetchMe]);

  useEffect(() => {
    const interceptor = api.interceptors.response.use(
      (response) => response,
      async (error) => {
        const originalRequest = error.config;
        if (error?.response?.status === 401 && !originalRequest?._retry) {
          originalRequest._retry = true;
          try {
            const refreshed = await authApi.refresh();
            setAccessToken(refreshed.access_token);
            originalRequest.headers = {
              ...(originalRequest.headers || {}),
              Authorization: `Bearer ${refreshed.access_token}`,
            };
            return api(originalRequest);
          } catch {
            setAccessToken(null);
            setUser(null);
          }
        }
        return Promise.reject(error);
      },
    );

    return () => {
      api.interceptors.response.eject(interceptor);
    };
  }, []);

  useEffect(() => {
    ensureSession().finally(() => setLoading(false));
  }, [ensureSession]);

  const signup = async (payload: SignupPayload) => {
    await authApi.signup(payload);
  };

  const verifyOtp = async (payload: VerifyOtpPayload) => {
    await authApi.verifyOtp(payload);
  };

  const login = async (payload: LoginPayload) => {
    const token = await authApi.login(payload);
    setAccessToken(token.access_token);
    await fetchMe(token.access_token);
  };

  const logout = async () => {
    await authApi.logout();
    setAccessToken(null);
    setUser(null);
  };

  const refreshMe = useCallback(async () => {
    if (!accessToken) return;
    await fetchMe(accessToken);
  }, [accessToken, fetchMe]);

  const requestLoginOtp = async (email: string) => {
    await authApi.requestLoginOtp({ email });
  };

  const verifyLoginOtp = async (payload: LoginOtpVerifyPayload) => {
    const token = await authApi.verifyLoginOtp(payload);
    setAccessToken(token.access_token);
    await fetchMe(token.access_token);
  };

  const startGoogleSSO = () => {
    window.location.href = `${import.meta.env.VITE_API_BASE_URL}/auth/google/login`;
  };

  const startMicrosoftSSO = () => {
    window.location.href = `${import.meta.env.VITE_API_BASE_URL}/auth/microsoft/login`;
  };

  const value = useMemo(
    () => ({
      accessToken,
      user,
      loading,
      signup,
      verifyOtp,
      login,
      requestLoginOtp,
      verifyLoginOtp,
      logout,
      ensureSession,
      refreshMe,
      startGoogleSSO,
      startMicrosoftSSO,
    }),
    [accessToken, user, loading, ensureSession, refreshMe],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used inside AuthProvider');
  }
  return ctx;
};
