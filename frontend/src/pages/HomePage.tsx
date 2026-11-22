import React, { useEffect, useState } from 'react';
import api from '../api/client';

interface HealthData {
  status: string;
  app: string;
  version: string;
  database?: string;
}

export const HomePage: React.FC = () => {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<HealthData>('/health')
      .then((res) => {
        setHealth(res.data);
        setError(null);
      })
      .catch((err) => {
        setError(err.message || 'Failed to reach backend');
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);

  return (
    <div className="flex flex-col items-center justify-center min-h-screen p-6 bg-slate-50">
      <div className="max-w-md w-full bg-white rounded-2xl shadow-lg p-8 border border-slate-100">
        <div className="flex items-center space-x-3 mb-4">
          <div className="h-10 w-10 rounded-xl bg-blue-600 flex items-center justify-center text-white font-bold text-xl shadow-md">
            F
          </div>
          <div>
            <h1 className="text-2xl font-bold text-slate-800">Frontdesk</h1>
            <p className="text-xs text-slate-500 font-medium">FastAPI + React + MySQL</p>
          </div>
        </div>

        <div className="space-y-4 mb-6">
          <div className="p-4 rounded-xl bg-slate-50 border border-slate-200">
            <h2 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-3">
              Service Status
            </h2>
            {loading && <p className="text-sm text-slate-500 animate-pulse">Checking health...</p>}
            {error && (
              <div className="text-sm text-red-600 bg-red-50 p-3 rounded-lg border border-red-200 font-medium">
                Backend connection failed: {error}
              </div>
            )}
            {health && (
              <div className="text-sm space-y-2">
                <div className="flex justify-between items-center">
                  <span className="text-slate-600 font-medium">Backend API:</span>
                  <span className="px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800">
                    {health.status} ({health.app})
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-slate-600 font-medium">MySQL Database:</span>
                  <span
                    className={`px-2 py-0.5 rounded-full text-xs font-semibold ${
                      health.database === 'connected'
                        ? 'bg-emerald-100 text-emerald-800'
                        : 'bg-amber-100 text-amber-800'
                    }`}
                  >
                    {health.database || 'connected'}
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-slate-600 font-medium">Version:</span>
                  <span className="text-slate-700 font-mono text-xs">{health.version}</span>
                </div>
              </div>
            )}
          </div>

          <div className="grid grid-cols-2 gap-3 text-xs">
            <a
              href="http://localhost:8000/docs"
              target="_blank"
              rel="noreferrer"
              className="p-3 text-center rounded-xl bg-blue-50 text-blue-700 font-semibold border border-blue-100 hover:bg-blue-100 transition-colors"
            >
              Swagger Docs (/docs) →
            </a>
            <a
              href="http://localhost:8000/health"
              target="_blank"
              rel="noreferrer"
              className="p-3 text-center rounded-xl bg-slate-100 text-slate-700 font-semibold border border-slate-200 hover:bg-slate-200 transition-colors"
            >
              GET /health →
            </a>
          </div>
        </div>
      </div>
    </div>
  );
};
