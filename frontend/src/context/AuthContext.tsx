import React, { createContext, useContext, useState, useEffect } from 'react';
import { Agent } from '../types';
import api from '../api/client';

interface AuthContextType {
  agent: Agent | null;
  token: string | null;
  login: (token: string, agent: Agent) => void;
  logout: () => void;
  loading: boolean;
}

const AuthContext = createContext<AuthContextType>({
  agent: null,
  token: null,
  login: () => {},
  logout: () => {},
  loading: true,
});

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [agent, setAgent] = useState<Agent | null>(null);
  const [token, setToken] = useState<string | null>(localStorage.getItem('token'));
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    if (token) {
      api
        .get<Agent>('/auth/me')
        .then((res) => {
          setAgent(res.data);
          localStorage.setItem('agent', JSON.stringify(res.data));
        })
        .catch(() => {
          logout();
        })
        .finally(() => {
          setLoading(false);
        });
    } else {
      setLoading(false);
    }
  }, [token]);

  const login = (newToken: string, newAgent: Agent) => {
    localStorage.setItem('token', newToken);
    localStorage.setItem('agent', JSON.stringify(newAgent));
    setToken(newToken);
    setAgent(newAgent);
  };

  const logout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('agent');
    setToken(null);
    setAgent(null);
  };

  return (
    <AuthContext.Provider value={{ agent, token, login, logout, loading }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
