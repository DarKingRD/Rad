import React, { useState } from 'react';
import { Sidebar } from './components/layout/Sidebar';
import { Header } from './components/layout/Header';
import { DashboardView } from './components/dashboard/DashboardView';
import { ShiftPlanningView } from './components/planning/ShiftPlanningView';
import { CurrentDistributionView } from './components/distribution/CurrentDistributionView';
import { DoctorsView } from './components/doctors/DoctorsView';
import { ReportsView } from './components/reports/ReportsView';

export default function App() {
  const [activeTab, setActiveTab] = useState('dashboard');

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

  return (
    <div className="flex h-screen bg-slate-50 font-sans text-slate-900">
      <Sidebar activeTab={activeTab} setActiveTab={setActiveTab} />
      
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
        
        <main className="flex-1 overflow-y-auto p-8">
          <div className="max-w-7xl mx-auto">
            {renderContent()}
          </div>
        </main>
      </div>
    </div>
  );
}