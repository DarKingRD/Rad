import { FormEvent, useState } from 'react';
import { Activity, LockKeyhole } from 'lucide-react';
import { authApi, ApiClientError } from '../../services/api';

type LoginViewProps = {
  onSuccess: () => void;
};

export function LoginView({ onSuccess }: LoginViewProps) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setIsLoading(true);

    try {
      await authApi.login(username, password);
      onSuccess();
    } catch (err) {
      const message = err instanceof ApiClientError ? err.message : 'Ошибка авторизации';
      setError(message);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-dvh bg-gradient-to-br from-slate-50 via-white to-blue-100/60 px-4 py-8 flex items-center justify-center">
      <div className="w-full max-w-md">
        <div className="mb-6 flex items-center justify-center gap-2 text-blue-600">
          <Activity size={30} />
          <span className="text-2xl font-bold tracking-tight text-slate-950">РадПлан</span>
        </div>

        <form onSubmit={handleSubmit} className="rounded-3xl border border-slate-200/80 bg-white/90 p-5 shadow-xl shadow-slate-200/70 backdrop-blur sm:p-8">
          <div className="mb-6 rounded-2xl bg-blue-50 p-4 text-blue-800">
            <div className="mb-2 flex h-10 w-10 items-center justify-center rounded-2xl bg-white text-blue-600 shadow-sm">
              <LockKeyhole size={20} />
            </div>
            <h1 className="text-xl font-semibold text-slate-950 sm:text-2xl">Вход в РадПлан</h1>
            <p className="mt-1 text-sm text-slate-600">Для руководителя и врачей службы.</p>
          </div>

          <div className="space-y-4">
            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-700">Логин</label>
              <input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full rounded-xl border border-slate-300 px-3 py-2.5 text-slate-900 transition focus:border-blue-500 focus:outline-none focus:ring-4 focus:ring-blue-100"
                required
              />
            </div>

            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-700">Пароль</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded-xl border border-slate-300 px-3 py-2.5 text-slate-900 transition focus:border-blue-500 focus:outline-none focus:ring-4 focus:ring-blue-100"
                required
              />
            </div>
          </div>

          {error ? (
            <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-700">
              {error}
            </div>
          ) : null}

          <button
            type="submit"
            disabled={isLoading}
            className="mt-6 w-full rounded-xl bg-blue-600 py-3 font-semibold text-white shadow-sm shadow-blue-600/20 transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isLoading ? 'Входим...' : 'Войти'}
          </button>
        </form>
      </div>
    </div>
  );
}
