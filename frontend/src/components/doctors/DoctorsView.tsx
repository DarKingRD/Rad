import React, { useState, useEffect } from 'react';
import { doctorsApi } from '../../services/api';
import { Plus } from 'lucide-react';
import { Doctor } from '../../types';

export const DoctorsView: React.FC = () => {
  const [doctors, setDoctors] = useState<Doctor[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadDoctors();
  }, []);

const loadDoctors = async () => {
  try {
    setLoading(true);
    const res = await doctorsApi.getAll();
    
    // ✅ ИСПРАВЛЕНО: берём данные из results (для пагинации DRF)
    const doctorsData = res.data.results || res.data;
    
    console.log('Doctors API response:', doctorsData);
    setDoctors(Array.isArray(doctorsData) ? doctorsData : []);
  } catch (err: any) {
    console.error('Error loading doctors:', err);
    console.error('Status:', err.response?.status);
    console.error('Data:', err.response?.data);
  } finally {
    setLoading(false);
  }
};

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-slate-500">Загрузка врачей...</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-bold text-slate-900">Справочник врачей ({doctors.length})</h2>
        <button className="px-4 py-2 bg-blue-600 text-white rounded-md text-sm font-medium hover:bg-blue-700 flex items-center">
          <Plus size={16} className="mr-2" /> Добавить врача
        </button>
      </div>

      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 border-b border-slate-200">
            <tr>
              <th className="px-6 py-4 font-semibold text-slate-700">ФИО</th>
              <th className="px-6 py-4 font-semibold text-slate-700">Специализация</th>
              <th className="px-6 py-4 font-semibold text-slate-700">Макс. УП/день</th>
              <th className="px-6 py-4 font-semibold text-slate-700">Статус</th>
              <th className="px-6 py-4 font-semibold text-slate-700 text-right">Действия</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {doctors.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-6 py-8 text-center text-slate-500">
                  Врачи не найдены
                </td>
              </tr>
            ) : (
              doctors.map((doc) => (
                <tr key={doc.id} className="hover:bg-slate-50">
                  <td className="px-6 py-4 font-medium text-slate-900">{doc.fio_alias || 'Не указано'}</td>
                  <td className="px-6 py-4 text-slate-600">{doc.specialty}</td>
                  <td className="px-6 py-4 text-slate-600">{doc.max_up_per_day || 120}</td>
                  <td className="px-6 py-4">
                    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                      doc.is_active ? 'bg-green-100 text-green-800' : 'bg-slate-100 text-slate-800'
                    }`}>
                      {doc.is_active ? 'Активен' : 'В архиве'}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-right">
                    <button className="text-slate-400 hover:text-blue-600">Ред.</button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};