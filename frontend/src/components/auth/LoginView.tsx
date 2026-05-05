import { FormEvent, useState } from 'react';
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
    <div className="min-h-screen bg-slate-100 flex items-center justify-center px-4">
      <form onSubmit={handleSubmit} className="w-full max-w-md bg-white shadow-lg rounded-2xl p-8 space-y-5">
        <h1 className="text-2xl font-semibold text-slate-900">Вход для руководителя службы</h1>
        <p className="text-sm text-slate-500">Введите учетные данные для доступа к RadPlan.</p>

        <div>
          <label className="block text-sm font-medium mb-1">Логин</label>
          <input value={username} onChange={(e) => setUsername(e.target.value)} className="w-full border rounded-lg px-3 py-2" required />
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">Пароль</label>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} className="w-full border rounded-lg px-3 py-2" required />
        </div>

        {error ? <p className="text-sm text-rose-600">{error}</p> : null}

        <button type="submit" disabled={isLoading} className="w-full bg-blue-600 text-white rounded-lg py-2.5 font-medium disabled:opacity-60">
          {isLoading ? 'Входим...' : 'Войти'}
        </button>
      </form>
    </div>
  );
}