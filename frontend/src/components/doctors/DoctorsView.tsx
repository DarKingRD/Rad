import React, { useState, useEffect } from 'react';
import { doctorsApi } from '../../services/api';
import { Plus, X } from 'lucide-react';
import { Doctor } from '../../types';

interface DoctorFormData {
  fio_alias: string;
  position_type: string;
  max_up_per_day: number;
  is_active: boolean;
  modality: string[];
}

export const DoctorsView: React.FC = () => {
  const [doctors, setDoctors] = useState<Doctor[]>([]);
  const [loading, setLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingDoctor, setEditingDoctor] = useState<Doctor | null>(null);
  const [formData, setFormData] = useState<DoctorFormData>({
    fio_alias: '',
    position_type: 'radiologist',
    max_up_per_day: 120,
    is_active: true,
    modality: [] as string[],
  });

  useEffect(() => {
    loadDoctors();
  }, []);

  const loadDoctors = async () => {
    try {
      setLoading(true);
      const res = await doctorsApi.getAll();
      const doctorsData = res.data.results || res.data;
      setDoctors(Array.isArray(doctorsData) ? doctorsData : []);
    } catch (err: any) {
      console.error('Error loading doctors:', err);
    } finally {
      setLoading(false);
    }
  };

  const getDefaultFormData = (): DoctorFormData => ({
    fio_alias: '',
    position_type: 'radiologist',
    max_up_per_day: 120,
    is_active: true,
    modality: [],
  });

  const handleOpenModal = (doctor?: Doctor) => {
    if (doctor) {
      setEditingDoctor(doctor);
      setFormData({
        fio_alias: doctor.fio_alias || '',
        position_type: doctor.position_type || 'radiologist',
        max_up_per_day: doctor.max_up_per_day || 50,
        modality: doctor.modality || [],
        is_active: doctor.is_active !== undefined ? doctor.is_active : true,
      });
    } else {
      setEditingDoctor(null);
      setFormData(getDefaultFormData());
    }
    setIsModalOpen(true);
  };

  const handleCloseModal = () => {
    setIsModalOpen(false);
    setEditingDoctor(null);
    setFormData(getDefaultFormData());
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      if (editingDoctor) {
        await doctorsApi.update(editingDoctor.id, formData);
      } else {
        await doctorsApi.create(formData);
      }
      await loadDoctors();
      handleCloseModal();
    } catch (error: any) {
      console.error('Error saving doctor:', error);
      alert('Ошибка при сохранении врача: ' + (error.response?.data?.detail || error.message));
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
        <button 
          onClick={() => handleOpenModal()}
          className="px-4 py-2 bg-blue-600 text-white rounded-md text-sm font-medium hover:bg-blue-700 flex items-center"
        >
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
              <th className="px-6 py-4 font-semibold text-slate-700">Модальности</th>
              <th className="px-6 py-4 font-semibold text-slate-700">Статус</th>
              <th className="px-6 py-4 font-semibold text-slate-700 text-right">Действия</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {doctors.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-6 py-8 text-center text-slate-500">
                  Врачи не найдены
                </td>
              </tr>
            ) : (
              doctors.map((doc) => (
                <tr key={doc.id} className="hover:bg-slate-50">
                  <td className="px-6 py-4 font-medium text-slate-900">{doc.fio_alias || 'Не указано'}</td>
                  <td className="px-6 py-4 text-slate-600">{doc.specialty}</td>
                  <td className="px-6 py-4 text-slate-600">{doc.max_up_per_day || 120}</td>
                  <td className="px-6 py-4 text-slate-600">
                    {doc.modality && doc.modality.length > 0 ? (
                      <div className="flex flex-wrap gap-1">
                        {doc.modality.map((mod, index) => (
                          <span
                            key={index}
                            className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800"
                          >
                            {mod}
                          </span>
                        ))}
                      </div>
                    ) : (
                      <span className="text-slate-400">Не указано</span>
                    )}
                  </td>
                  <td className="px-6 py-4">
                    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                      doc.is_active ? 'bg-green-100 text-green-800' : 'bg-slate-100 text-slate-800'
                    }`}>
                      {doc.is_active ? 'Активен' : 'В архиве'}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-right">
                    <button 
                      onClick={() => handleOpenModal(doc)}
                      className="text-slate-400 hover:text-blue-600"
                    >
                      Ред.
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Модальное окно для добавления/редактирования врача */}
      {isModalOpen && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-xl max-w-md w-full mx-4">
            <div className="flex justify-between items-center p-6 border-b border-slate-200">
              <h3 className="text-xl font-bold text-slate-900">
                {editingDoctor ? 'Редактировать врача' : 'Добавить врача'}
              </h3>
              <button
                onClick={handleCloseModal}
                className="text-slate-400 hover:text-slate-600"
              >
                <X size={24} />
              </button>
            </div>
            
            <form onSubmit={handleSubmit} className="p-6 space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  ФИО
                </label>
                <input
                  type="text"
                  value={formData.fio_alias}
                  onChange={(e) => setFormData({ ...formData, fio_alias: e.target.value })}
                  className="w-full px-3 py-2 border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  required
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Специализация
                </label>
                <select
                  value={formData.position_type}
                  onChange={(e) => setFormData({ ...formData, position_type: e.target.value })}
                  className="w-full px-3 py-2 border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="radiologist">Рентгенолог</option>
                  <option value="diagnostician">КТ-диагност</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Макс. УП/день
                </label>
                <input
                  type="number"
                  value={formData.max_up_per_day}
                  onChange={(e) => setFormData({ ...formData, max_up_per_day: parseInt(e.target.value) || 120 })}
                  className="w-full px-3 py-2 border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  min="1"
                  required
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Модальности (через пробел)
                </label>
                <input
                  type="text"
                  value={(formData.modality || []).join(' ')}
                  onChange={(e) =>
                    setFormData({
                      ...formData,
                      modality: e.target.value.split(',').map((m) => m.trim()).filter(Boolean),
                    })
                  }
                  className="w-full px-3 py-2 border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="КТ МРТ Рентген"
                />
            </div>

              <div className="flex items-center">
                <input
                  type="checkbox"
                  id="is_active"
                  checked={formData.is_active}
                  onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                  className="w-4 h-4 text-blue-600 border-slate-300 rounded focus:ring-blue-500"
                />
                <label htmlFor="is_active" className="ml-2 text-sm font-medium text-slate-700">
                  Активен
                </label>
              </div>

              <div className="flex space-x-3 pt-4">
                <button
                  type="submit"
                  className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-md font-medium hover:bg-blue-700"
                >
                  {editingDoctor ? 'Сохранить' : 'Добавить'}
                </button>
                <button
                  type="button"
                  onClick={handleCloseModal}
                  className="flex-1 px-4 py-2 bg-slate-200 text-slate-700 rounded-md font-medium hover:bg-slate-300"
                >
                  Отмена
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};