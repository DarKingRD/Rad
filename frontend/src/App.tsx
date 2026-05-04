import { useState } from 'react';
import { Sidebar } from './components/layout/Sidebar';
import { Header } from './components/layout/Header';
import { DashboardView } from './components/dashboard/DashboardView';
import { ShiftPlanningView } from './components/planning/ShiftPlanningView';
import CurrentDistributionView  from './components/distribution/CurrentDistributionView';
import { DoctorsView } from './components/doctors/DoctorsView';
import { ReportsView } from './components/reports/ReportsView';
import {LoginView} from './components/auth/LoginView';
import {authApi } from './services/api';

export default function App() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [isAuthenticated, setIsAuthenticated] = useState(authApi.isAuthenticated());
  const currentUser = authApi.getCurrentUser();
  const renderContent = () => {
    switch (activeTab) {
      case 'dashboard': return <DashboardView />;
      case 'planning': return <ShiftPlanningView />;
      case 'distribution': return <CurrentDistributionView />;
      case 'doctors': return <DoctorsView />;
      case 'reports': return <ReportsView />;
      default: return <DashboardView />;
    }
  };

  const handleRefresh = () => {
    window.location.reload();
  };

    const handleLogout = () => {
    authApi.logout();
    setIsAuthenticated(false);
  };

  if (!isAuthenticated) {
    return <LoginView onSuccess={() => setIsAuthenticated(true)} />;
  }

  const accountName = currentUser?.full_name || currentUser?.username || 'Руководитель службы';
  const accountRole = currentUser?.username ? `Логин: ${currentUser.username}` : 'Авторизованный пользователь';

  return (
    <div className="flex h-screen bg-slate-50 font-sans text-slate-900">
      <Sidebar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        accountName={accountName}
        accountRole={accountRole}
        onLogout={handleLogout}
      />
      
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header 
          currentDate={new Date().toLocaleDateString('ru-RU', { 
            day: 'numeric', 
            month: 'long', 
            year: 'numeric',
            weekday: 'long'
          })} 
          onRefresh={handleRefresh}
        />
        <div className="px-8 pt-4">
        </div>
        <main className="flex-1 overflow-y-auto p-8">
          <div className="max-w-7xl mx-auto">
            {renderContent()}
          </div>
        </main>
      </div>
    </div>
  );
}