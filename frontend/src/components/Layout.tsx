import React from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export const Layout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { agent, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 flex flex-col font-sans">
      <header className="bg-white border-b border-slate-200 sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center space-x-6">
            <Link to="/" className="flex items-center space-x-3">
              <div className="h-9 w-9 rounded-lg bg-blue-600 flex items-center justify-center text-white font-bold text-lg shadow-sm">
                F
              </div>
              <span className="font-bold text-lg text-slate-900">Frontdesk</span>
            </Link>
            <nav className="flex space-x-4">
              <Link
                to="/"
                className="text-sm font-semibold text-slate-700 hover:text-blue-600 transition"
              >
                Tickets
              </Link>
            </nav>
          </div>

          <div className="flex items-center space-x-4">
            {agent && (
              <div className="text-right hidden sm:block">
                <div className="text-sm font-medium text-slate-800">{agent.name}</div>
                <div className="text-xs text-slate-500 capitalize">{agent.role}</div>
              </div>
            )}
            <button
              onClick={() => {
                logout();
                navigate('/login');
              }}
              className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 transition"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {children}
      </main>
    </div>
  );
};
