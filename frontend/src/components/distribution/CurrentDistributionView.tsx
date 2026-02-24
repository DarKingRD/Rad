import React, { useState, useEffect, useMemo } from 'react';
import { studiesApi, doctorsApi } from '../../services/api';
import { UserCheck, ChevronLeft, ChevronRight } from 'lucide-react';
import { Study, DoctorWithLoad } from '../../types';

export const CurrentDistributionView: React.FC = () => {
  const [selectedStudy, setSelectedStudy] = useState<Study | null>(null);
  const [allStudies, setAllStudies] = useState<Study[]>([]);
  const [doctors, setDoctors] = useState<DoctorWithLoad[]>([]);
  const [loading, setLoading] = useState(true);
  const [currentPage, setCurrentPage] = useState(1);
  const [itemsPerPage] = useState(20);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [studiesRes, doctorsRes] = await Promise.all([
        studiesApi.getPending(),
        doctorsApi.getWithLoad()
      ]);
      setAllStudies(studiesRes.data || []);
      setDoctors(doctorsRes.data);
    } catch (error) {
      console.error('Error loading data:', error);
    } finally {
      setLoading(false);
    }
  };

  // Сортировка исследований: CITO -> ASAP -> План
  const sortedStudies = useMemo(() => {
    return [...allStudies].sort((a, b) => {
      const getPriorityOrder = (study: Study): number => {
        if (study.priority === 'cito') return 1;
        if (study.priority === 'asap') return 2;
        return 3;
      };
      
      const orderA = getPriorityOrder(a);
      const orderB = getPriorityOrder(b);
      
      if (orderA !== orderB) {
        return orderA - orderB;
      }
      
      // Если приоритет одинаковый, сортируем по дате создания (новые первыми)
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
    });
  }, [allStudies]);

  // Пагинация
  const totalPages = Math.ceil(sortedStudies.length / itemsPerPage);
  const startIndex = (currentPage - 1) * itemsPerPage;
  const endIndex = startIndex + itemsPerPage;
  const paginatedStudies = sortedStudies.slice(startIndex, endIndex);

  const handlePageChange = (page: number) => {
    setCurrentPage(page);
    setSelectedStudy(null);
    setSelectedDoctor(null);
  };

  const getPriorityColor = (study: Study) => {
    if (study.priority === 'cito') return 'bg-red-100 text-red-700';
    if (study.priority === 'asap') return 'bg-amber-100 text-amber-700';
    return 'bg-slate-100 text-slate-600';
  };

  const getPriorityLabel = (study: Study) => {
    if (study.priority === 'cito') return 'CITO';
    if (study.priority === 'asap') return 'ASAP';
    return 'План';
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'confirmed': case 'Подтверждено': return 'bg-green-100 text-green-700';
      case 'signed': case 'Подписано': return 'bg-blue-100 text-blue-700';
      default: return 'bg-slate-100 text-slate-600';
    }
  };

  const [selectedDoctor, setSelectedDoctor] = useState<number | null>(null);

  const handleAssign = async (doctor_id?: number) => {
    if (!selectedStudy) return;
    const targetDoctorId = doctor_id || selectedDoctor;
    if (!targetDoctorId) {
      alert('Выберите врача');
      return;
    }
    try {
      await studiesApi.assign(selectedStudy.id, targetDoctorId);
      await loadData();
      setSelectedStudy(null);
      setSelectedDoctor(null);
    } catch (error) {
      console.error('Error assigning study:', error);
      alert('Ошибка при назначении');
    }
  };

  const handleDoctorClick = (doctorId: number) => {
    if (selectedStudy) {
      setSelectedDoctor(doctorId);
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
            Очередь исследований ({sortedStudies.length})
          </h3>
        </div>
        
        <div className="flex-1 overflow-y-auto p-2 space-y-2">
          {paginatedStudies.length === 0 ? (
            <div className="p-8 text-center text-slate-500">
              Нет исследований в очереди
            </div>
          ) : (
            paginatedStudies.map((study) => (
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

        {/* Пагинация */}
        {totalPages > 1 && (
          <div className="p-4 border-t border-slate-200 flex items-center justify-between">
            <div className="text-sm text-slate-600">
              Показано {startIndex + 1}-{Math.min(endIndex, sortedStudies.length)} из {sortedStudies.length}
            </div>
            <div className="flex items-center space-x-2">
              <button
                onClick={() => handlePageChange(currentPage - 1)}
                disabled={currentPage === 1}
                className={`p-2 rounded-md border ${
                  currentPage === 1
                    ? 'border-slate-200 text-slate-400 cursor-not-allowed'
                    : 'border-slate-300 text-slate-700 hover:bg-slate-50'
                }`}
              >
                <ChevronLeft size={16} />
              </button>
              
              <div className="flex items-center space-x-1">
                {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                  let pageNum: number;
                  if (totalPages <= 5) {
                    pageNum = i + 1;
                  } else if (currentPage <= 3) {
                    pageNum = i + 1;
                  } else if (currentPage >= totalPages - 2) {
                    pageNum = totalPages - 4 + i;
                  } else {
                    pageNum = currentPage - 2 + i;
                  }
                  
                  return (
                    <button
                      key={pageNum}
                      onClick={() => handlePageChange(pageNum)}
                      className={`px-3 py-1 rounded-md text-sm ${
                        currentPage === pageNum
                          ? 'bg-blue-600 text-white'
                          : 'border border-slate-300 text-slate-700 hover:bg-slate-50'
                      }`}
                    >
                      {pageNum}
                    </button>
                  );
                })}
              </div>
              
              <button
                onClick={() => handlePageChange(currentPage + 1)}
                disabled={currentPage === totalPages}
                className={`p-2 rounded-md border ${
                  currentPage === totalPages
                    ? 'border-slate-200 text-slate-400 cursor-not-allowed'
                    : 'border-slate-300 text-slate-700 hover:bg-slate-50'
                }`}
              >
                <ChevronRight size={16} />
              </button>
            </div>
          </div>
        )}
      </div>

      <div className="w-1/2 space-y-4 flex flex-col">
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
                  onClick={() => handleDoctorClick(doc.id)}
                  className={`flex items-center justify-between p-3 border rounded-lg cursor-pointer transition-all ${
                    selectedDoctor === doc.id && selectedStudy
                      ? 'border-blue-500 bg-blue-50 ring-2 ring-blue-200'
                      : 'border-slate-100 hover:bg-slate-50'
                  }`}
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

        {selectedStudy && (
          <div className="bg-blue-600 text-white p-4 rounded-xl shadow-lg">
            <h4 className="font-medium mb-2">Действия для: {selectedStudy.research_number}</h4>
            <p className="text-blue-100 text-sm mb-4">
              Статус: <strong>{selectedStudy.status}</strong> | 
              Приоритет: <strong>{getPriorityLabel(selectedStudy)}</strong>
            </p>
            {selectedDoctor && (
              <p className="text-blue-100 text-sm mb-3">
                Выбран врач: <strong>{doctors.find(d => d.id === selectedDoctor)?.fio_alias}</strong>
              </p>
            )}
            <div className="flex space-x-3">
              {selectedDoctor ? (
                <>
                  <button 
                    onClick={() => handleAssign()}
                    className="flex-1 bg-white text-blue-600 py-2 rounded-md font-medium text-sm hover:bg-blue-50"
                  >
                    Назначить выбранному врачу
                  </button>
                  <button 
                    onClick={() => setSelectedDoctor(null)}
                    className="px-4 py-2 bg-blue-500 text-white rounded-md font-medium text-sm hover:bg-blue-400"
                  >
                    Сбросить выбор
                  </button>
                </>
              ) : (
                <button 
                  onClick={() => handleAssign(doctors[0]?.id)}
                  className="flex-1 bg-white text-blue-600 py-2 rounded-md font-medium text-sm hover:bg-blue-50"
                >
                  Назначить автоматически
                </button>
              )}
              <button 
                onClick={() => {
                  setSelectedStudy(null);
                  setSelectedDoctor(null);
                }}
                className="flex-1 bg-blue-700 text-white border border-blue-500 py-2 rounded-md font-medium text-sm hover:bg-blue-800"
              >
                Отмена
              </button>
            </div>
            <p className="text-blue-100 text-xs mt-3">
              💡 Выберите врача из списка выше, затем нажмите "Назначить выбранному врачу"
            </p>
          </div>
        )}
      </div>
    </div>
  );
};