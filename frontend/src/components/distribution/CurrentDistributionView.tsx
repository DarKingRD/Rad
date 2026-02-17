import React, { useState, useEffect } from 'react';
import { studiesApi, doctorsApi } from '../../services/api';
import { Filter, UserCheck } from 'lucide-react';
import { Study, DoctorWithLoad } from '../../types';

export const CurrentDistributionView: React.FC = () => {
  const [selectedStudy, setSelectedStudy] = useState<Study | null>(null);
  const [studies, setStudies] = useState<Study[]>([]);
  const [doctors, setDoctors] = useState<DoctorWithLoad[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [studiesRes, doctorsRes] = await Promise.all([
        studiesApi.getPending(),
        doctorsApi.getWithLoad()
      ]);
      setStudies(studiesRes.data);
      setDoctors(doctorsRes.data);
    } catch (error) {
      console.error('Error loading data:', error);
    } finally {
      setLoading(false);
    }
  };

  const getPriorityColor = (study: Study) => {
    if (study.is_cito || study.priority === 'cito') return 'bg-red-100 text-red-700';
    if (study.is_asap || study.priority === 'asap') return 'bg-amber-100 text-amber-700';
    return 'bg-slate-100 text-slate-600';
  };

  const getPriorityLabel = (study: Study) => {
    if (study.is_cito || study.priority === 'cito') return 'CITO';
    if (study.is_asap || study.priority === 'asap') return 'ASAP';
    return 'План';
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'confirmed': case 'Подтверждено': return 'bg-green-100 text-green-700';
      case 'signed': case 'Подписано': return 'bg-blue-100 text-blue-700';
      default: return 'bg-slate-100 text-slate-600';
    }
  };

  const handleAssign = async (doctor_id: number) => {
    if (!selectedStudy) return;
    try {
      await studiesApi.assign(selectedStudy.id, doctor_id);
      loadData();
      setSelectedStudy(null);
    } catch (error) {
      console.error('Error assigning study:', error);
      alert('Ошибка при назначении');
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-slate-500">Загрузка...</div>
      </div>
    );
  }

  return (
    <div className="h-[calc(100vh-140px)] flex space-x-6">
      {/* Worklist — Очередь исследований */}
      <div className="w-1/2 bg-white rounded-xl border border-slate-200 shadow-sm flex flex-col">
        <div className="p-4 border-b border-slate-200 flex justify-between items-center">
          <h3 className="font-semibold text-slate-800">
            Очередь исследований ({studies.length})
          </h3>
          <div className="flex space-x-2">
            <input 
              type="text" 
              placeholder="Поиск..." 
              className="px-3 py-1.5 border border-slate-300 rounded-md text-sm" 
            />
            <button className="p-1.5 bg-slate-100 rounded-md hover:bg-slate-200">
              <Filter size={16} />
            </button>
          </div>
        </div>
        
        {/* ✅ СКРОЛЛ ДЛЯ ИССЛЕДОВАНИЙ */}
        <div className="flex-1 overflow-y-auto p-2 space-y-2">
          {studies.length === 0 ? (
            <div className="p-8 text-center text-slate-500">
              Нет исследований в очереди
            </div>
          ) : (
            studies.map((study) => (
              <div 
                key={study.id}
                onClick={() => setSelectedStudy(study)}
                className={`p-4 rounded-lg border cursor-pointer transition-all ${
                  selectedStudy?.id === study.id 
                    ? 'border-blue-500 bg-blue-50 ring-1 ring-blue-500' 
                    : 'border-slate-200 hover:border-blue-300 hover:bg-slate-50'
                }`}
              >
                <div className="flex justify-between items-start mb-2">
                  <span className="font-medium text-slate-900">{study.research_number}</span>
                  <span className={`px-2 py-0.5 rounded text-xs font-medium ${getPriorityColor(study)}`}>
                    {getPriorityLabel(study)}
                  </span>
                </div>
                <div className="text-sm text-slate-600 mb-2">
                  Тип: {study.study_type?.name || `ID: ${study.study_type_id}`}
                </div>
                <div className="flex justify-between text-xs text-slate-400">
                  <span>Создано: {new Date(study.created_at).toLocaleDateString('ru-RU')}</span>
                  <span className={`px-2 py-0.5 rounded ${getStatusColor(study.status)}`}>
                    {study.status}
                  </span>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Doctors Status — Состояние врачей */}
      <div className="w-1/2 space-y-4 flex flex-col">
        {/* ✅ СКРОЛЛ ДЛЯ ВРАЧЕЙ */}
        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex-1 overflow-y-auto">
          <h3 className="font-semibold text-slate-800 mb-4 sticky top-0 bg-white">
            Состояние врачей ({doctors.length})
          </h3>
          <div className="space-y-3">
            {doctors.length === 0 ? (
              <div className="p-8 text-center text-slate-500">
                Нет активных врачей
              </div>
            ) : (
              doctors.map((doc) => (
                <div 
                  key={doc.id} 
                  className="flex items-center justify-between p-3 border border-slate-100 rounded-lg hover:bg-slate-50"
                >
                  <div className="flex items-center space-x-3">
                    <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center text-blue-700 font-bold">
                      {doc.fio_alias.charAt(0)}
                    </div>
                    <div>
                      <div className="font-medium text-slate-900">{doc.fio_alias}</div>
                      <div className="text-xs text-slate-500">{doc.specialty}</div>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-sm font-medium text-slate-900">
                      {doc.current_load} / {doc.max_load} УП
                    </div>
                    <div className="w-24 h-2 bg-slate-100 rounded-full mt-1 overflow-hidden">
                      <div 
                        className={`h-full ${doc.current_load / doc.max_load > 0.8 ? 'bg-red-500' : 'bg-green-500'}`} 
                        style={{ width: `${Math.min((doc.current_load / doc.max_load) * 100, 100)}%` }}
                      ></div>
                    </div>
                    <div className="text-xs text-green-600 mt-1 flex items-center justify-end">
                      <UserCheck size={12} className="mr-1" /> {doc.active_studies} исследований
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Панель действий для выбранного исследования */}
        {selectedStudy && (
          <div className="bg-blue-600 text-white p-4 rounded-xl shadow-lg">
            <h4 className="font-medium mb-2">Действия для: {selectedStudy.research_number}</h4>
            <p className="text-blue-100 text-sm mb-4">
              Статус: <strong>{selectedStudy.status}</strong> | 
              Приоритет: <strong>{getPriorityLabel(selectedStudy)}</strong>
            </p>
            <div className="flex space-x-3">
              <button 
                onClick={() => handleAssign(doctors[0]?.id)}
                className="flex-1 bg-white text-blue-600 py-2 rounded-md font-medium text-sm hover:bg-blue-50"
              >
                Назначить автоматически
              </button>
              <button 
                onClick={() => setSelectedStudy(null)}
                className="flex-1 bg-blue-700 text-white border border-blue-500 py-2 rounded-md font-medium text-sm hover:bg-blue-800"
              >
                Отмена
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};