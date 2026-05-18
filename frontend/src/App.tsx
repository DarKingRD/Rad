import { useState } from 'react';
import { Sidebar } from './components/layout/Sidebar';
import { Header } from './components/layout/Header';
import { DashboardView } from './components/dashboard/DashboardView';
import { ShiftPlanningView } from './components/planning/ShiftPlanningView';
import CurrentDistributionView  from './components/distribution/CurrentDistributionView';
import { DoctorsView } from './components/doctors/DoctorsView';
import { ReportsView } from './components/reports/ReportsView';
import {LoginView} from './components/auth/LoginView';
import { DoctorPortalView } from './components/doctor/DoctorPortalView';
import {authApi } from './services/api';

export default function App() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [refreshKey, setRefreshKey] = useState(0);
  const [isAuthenticated, setIsAuthenticated] = useState(authApi.isAuthenticated());
  const currentUser = authApi.getCurrentUser();
  const isDoctorAccount =
    currentUser?.role === 'doctor' ||
    Boolean(currentUser?.doctor_id) ||
    /^doctor_\d+$/i.test(currentUser?.username || '') ||
    /^\d+$/.test(currentUser?.username || '');
  const renderContent = () => {
    switch (activeTab) {
      case 'dashboard': return <DashboardView onNavigate={setActiveTab} />;
      case 'planning': return <ShiftPlanningView />;
      case 'distribution': return <CurrentDistributionView />;
      case 'doctors': return <DoctorsView />;
      case 'reports': return <ReportsView />;
      default: return <DashboardView />;
    }
  };

  const handleRefresh = () => {
    setRefreshKey((prev) => prev + 1);
  };

    const handleLogout = () => {
    authApi.logout();
    setIsAuthenticated(false);
  };

  if (!isAuthenticated) {
    return <LoginView onSuccess={() => setIsAuthenticated(true)} />;
  }

  if (isDoctorAccount) {
    return <DoctorPortalView onLogout={handleLogout} />;
  }

  const accountName = currentUser?.full_name || currentUser?.username || 'Руководитель службы';
  const accountRole = currentUser?.username ? `Логин: ${currentUser.username}` : 'Авторизованный пользователь';

  return (
    <div className="flex h-dvh overflow-hidden bg-gradient-to-br from-slate-50 via-white to-blue-50/40 font-sans text-slate-900">
      <Sidebar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        accountName={accountName}
        accountRole={accountRole}
        onLogout={handleLogout}
      />
      
      <div className="flex-1 flex min-w-0 flex-col overflow-hidden">
        <Header 
          currentDate={new Date().toLocaleDateString('ru-RU', { 
            day: 'numeric', 
            month: 'long', 
            year: 'numeric',
            weekday: 'long'
          })} 
          onRefresh={handleRefresh}
        />
        <main className="flex-1 overflow-y-auto px-4 py-4 pb-24 md:px-6 md:py-6 md:pb-6 xl:px-8">
          <div className="mx-auto w-full max-w-[1480px]">
            <div key={`${activeTab}-${refreshKey}`}>
              {renderContent()}
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
