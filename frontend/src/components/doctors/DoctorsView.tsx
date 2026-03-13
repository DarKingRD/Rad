import React, { useState, useEffect, useMemo } from 'react';
import { doctorsApi } from '../../services/api';
import { Plus, X, Search, ArrowUpDown } from 'lucide-react';
import { Doctor, DoctorWithLoad } from '../../types';

interface DoctorFormData {
  fio_alias: string;
  position_type: string;
  max_up_per_day: number;
  is_active: boolean;
  modality: string[];
}

type SortDirection = 'asc' | 'desc' | null;
type SortColumn = keyof DoctorWithLoad | 'modality_count' | null;

export const DoctorsView: React.FC = () => {
  const [doctors, setDoctors] = useState<DoctorWithLoad[]>([]);
  const [loading, setLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingDoctor, setEditingDoctor] = useState<Doctor | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [sortColumn, setSortColumn] = useState<SortColumn>(null);
  const [sortDirection, setSortDirection] = useState<SortDirection>(null);

  // Фильтрация и сортировка через useMemo — без лишних стейтов
  const sortedDoctors = useMemo(() => {
    let result = [...doctors];

    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase().trim();
      result = result.filter((doc) => {
        const fio = (doc.fio_alias || '').toLowerCase();
        const specialty = (doc.specialty || doc.position_type || '').toLowerCase();
        const modalities = (doc.modality || []).join(' ').toLowerCase();
        const status = doc.is_active ? 'активен' : 'в архиве';
        return (
          fio.includes(query) ||
          specialty.includes(query) ||
          modalities.includes(query) ||
          status.includes(query) ||
          String(doc.max_up_per_day || '').includes(query) ||
          String(doc.id || '').includes(query)
        );
      });
    }

    if (sortColumn && sortDirection) {
      result = result.sort((a, b) => {
        let valA: any;
        let valB: any;
        switch (sortColumn) {
          case 'fio_alias':
            valA = (a.fio_alias || '').toLowerCase();
            valB = (b.fio_alias || '').toLowerCase();
            break;
          case 'position_type':
          case 'specialty':
            valA = (a.specialty || a.position_type || '').toLowerCase();
            valB = (b.specialty || b.position_type || '').toLowerCase();
            break;
          case 'max_up_per_day':
            valA = a.max_up_per_day || 0;
            valB = b.max_up_per_day || 0;
            break;
          case 'current_load':
            valA = a.current_load || 0;
            valB = b.current_load || 0;
            break;
          case 'is_active':
            valA = a.is_active ? 1 : 0;
            valB = b.is_active ? 1 : 0;
            break;
          case 'modality_count':
            valA = (a.modality || []).length;
            valB = (b.modality || []).length;
            break;
          default:
            return 0;
        }
        if (valA < valB) return sortDirection === 'asc' ? -1 : 1;
        if (valA > valB) return sortDirection === 'asc' ? 1 : -1;
        return 0;
      });
    }

    return result;
  }, [doctors, searchQuery, sortColumn, sortDirection]);

  const [formData, setFormData] = useState<DoctorFormData>({
    fio_alias: '',
    position_type: 'radiologist',
    max_up_per_day: 120,
    is_active: true,
    modality: [],
  });

  useEffect(() => {
    loadDoctors();
  }, []);

  const handleSort = (column: SortColumn) => {
    if (sortColumn === column) {
      if (sortDirection === 'asc') {
        setSortDirection('desc');
      } else if (sortDirection === 'desc') {
        setSortColumn(null);
        setSortDirection(null);
      } else {
        setSortDirection('asc');
      }
    } else {
      setSortColumn(column);
      setSortDirection('asc');
    }
  };

  const getSortIcon = (column: SortColumn) => {
    if (sortColumn !== column) return <ArrowUpDown size={14} className="ml-1 opacity-30" />;
    if (sortDirection === 'asc') return <ArrowUpDown size={14} className="ml-1" />;
    if (sortDirection === 'desc') return <ArrowUpDown size={14} className="ml-1 rotate-180" />;
    return null;
  };

  const loadDoctors = async () => {
  try {
    setLoading(true);
    const doctorsData = await doctorsApi.getWithLoad();
    setDoctors(doctorsData);
  } catch (err) {
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
  } catch (error) {
    console.error('Error saving doctor:', error);
    const message = error instanceof Error ? error.message : 'Ошибка при сохранении врача';
    alert(message);
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
    <div className="space-y-6 p-6">
      {/* Заголовок + кнопка добавления */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
        <h2 className="text-xl md:text-2xl font-bold text-slate-900">
          Врачи
          <span className="ml-2 text-sm font-normal text-slate-400">({sortedDoctors.length})</span>
        </h2>
        <button
          onClick={() => handleOpenModal()}
          className="px-4 py-2.5 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors flex items-center gap-2 whitespace-nowrap shadow-sm self-start sm:self-auto"
        >
          <Plus size={18} /> Добавить врача
        </button>
      </div>

      {/* Поиск */}
      <div className="relative">
        <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none">
          <Search size={18} className="text-slate-400" />
        </div>
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="Поиск по ФИО, специализации..."
          className="w-full pl-11 pr-10 py-2.5 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all text-sm"
        />
        {searchQuery && (
          <button
            onClick={() => setSearchQuery('')}
            className="absolute inset-y-0 right-0 pr-3.5 flex items-center text-slate-400 hover:text-slate-600 transition-colors"
          >
            <X size={18} />
          </button>
        )}
      </div>

      {/* Таблица — только десктоп */}
      <div className="hidden md:block bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 border-b border-slate-200">
            <tr>
              <th className="px-6 py-4 font-semibold text-slate-700 cursor-pointer hover:bg-slate-100 transition-colors select-none" onClick={() => handleSort('fio_alias')}>
                <div className="flex items-center gap-1">ФИО {getSortIcon('fio_alias')}</div>
              </th>
              <th className="px-6 py-4 font-semibold text-slate-700 cursor-pointer hover:bg-slate-100 transition-colors select-none" onClick={() => handleSort('position_type')}>
                <div className="flex items-center gap-1">Специализация {getSortIcon('position_type')}</div>
              </th>
              <th className="px-6 py-4 font-semibold text-slate-700 cursor-pointer hover:bg-slate-100 transition-colors select-none" onClick={() => handleSort('max_up_per_day')}>
                <div className="flex items-center gap-1">Макс. УП/день {getSortIcon('max_up_per_day')}</div>
              </th>
              <th className="px-6 py-4 font-semibold text-slate-700 cursor-pointer hover:bg-slate-100 transition-colors select-none" onClick={() => handleSort('modality_count')}>
                <div className="flex items-center gap-1">Модальности {getSortIcon('modality_count')}</div>
              </th>
              <th className="px-6 py-4 font-semibold text-slate-700 cursor-pointer hover:bg-slate-100 transition-colors select-none" onClick={() => handleSort('is_active')}>
                <div className="flex items-center gap-1">Статус {getSortIcon('is_active')}</div>
              </th>
              <th className="px-6 py-4 font-semibold text-slate-700 cursor-pointer hover:bg-slate-100 transition-colors select-none" onClick={() => handleSort('current_load')}>
                <div className="flex items-center gap-1">Нагрузка за месяц (УП) {getSortIcon('current_load')}</div>
              </th>
              <th className="px-6 py-4 font-semibold text-slate-700 text-right">Действия</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {sortedDoctors.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-6 py-16 text-center text-slate-500">
                  {searchQuery ? 'По вашему запросу ничего не найдено' : 'Врачи не найдены'}
                </td>
              </tr>
            ) : (
              sortedDoctors.map((doc) => (
                <tr key={doc.id} className="hover:bg-slate-50 transition-colors">
                  <td className="px-6 py-4 font-medium text-slate-900">{doc.fio_alias || 'Не указано'}</td>
                  <td className="px-6 py-4 text-slate-600">{doc.specialty || doc.position_type || '—'}</td>
                  <td className="px-6 py-4 text-slate-600">{doc.max_up_per_day || 120}</td>
                  <td className="px-6 py-4 text-slate-600">
                    {doc.modality && doc.modality.length > 0 ? (
                      <div className="flex flex-wrap gap-1.5">
                        {doc.modality.map((mod, index) => (
                          <span key={index} className="inline-flex items-center px-2.5 py-0.5 rounded text-xs font-medium bg-blue-50 text-blue-800 border border-blue-200">{mod}</span>
                        ))}
                      </div>
                    ) : (
                      <span className="text-slate-400 italic">Не указано</span>
                    )}
                  </td>
                  <td className="px-6 py-4">
                    <span className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-medium ${doc.is_active ? 'bg-green-100 text-green-800 border border-green-200' : 'bg-slate-100 text-slate-700 border border-slate-200'}`}>
                      {doc.is_active ? 'Активен' : 'В архиве'}
                    </span>
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-2 min-w-[140px]">
                      <div className="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden">
                        <div className={`h-full rounded-full transition-all ${doc.load_percentage > 95 ? 'bg-red-500' : doc.load_percentage > 80 ? 'bg-amber-400' : 'bg-green-500'}`}
                          style={{ width: `${Math.min(doc.load_percentage, 100)}%` }} />
                      </div>
                      <span className="text-xs text-slate-600 whitespace-nowrap">{doc.current_load.toFixed(1)} / {doc.max_load} УП</span>
                    </div>
                  </td>
                  <td className="px-6 py-4 text-right">
                    <button onClick={() => handleOpenModal(doc)} className="text-blue-600 hover:text-blue-800 font-medium transition-colors">
                      Редактировать
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Карточки — только мобиле */}
      <div className="md:hidden space-y-3">
        {sortedDoctors.length === 0 ? (
          <div className="text-center py-12 text-slate-500">
            {searchQuery ? 'По вашему запросу ничего не найдено' : 'Врачи не найдены'}
          </div>
        ) : (
          sortedDoctors.map((doc) => (
            <div key={doc.id} className="bg-white rounded-xl border border-slate-200 shadow-sm p-4 space-y-3">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="font-semibold text-slate-900 text-sm">{doc.fio_alias || 'Не указано'}</div>
                  <div className="text-xs text-slate-500 mt-0.5">{doc.specialty || doc.position_type || '—'}</div>
                </div>
                <span className={`shrink-0 inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium ${doc.is_active ? 'bg-green-100 text-green-800 border border-green-200' : 'bg-slate-100 text-slate-700 border border-slate-200'}`}>
                  {doc.is_active ? 'Активен' : 'В архиве'}
                </span>
              </div>
              {doc.modality && doc.modality.length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {doc.modality.map((mod, i) => (
                    <span key={i} className="px-2 py-0.5 rounded text-[11px] font-medium bg-blue-50 text-blue-800 border border-blue-200">{mod}</span>
                  ))}
                </div>
              )}
              <div>
                <div className="flex justify-between text-xs text-slate-500 mb-1">
                  <span>Нагрузка за месяц</span>
                  <span className="font-medium text-slate-700">{doc.current_load.toFixed(1)} / {doc.max_load} УП</span>
                </div>
                <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                  <div className={`h-full rounded-full ${doc.load_percentage > 95 ? 'bg-red-500' : doc.load_percentage > 80 ? 'bg-amber-400' : 'bg-green-500'}`}
                    style={{ width: `${Math.min(doc.load_percentage, 100)}%` }} />
                </div>
              </div>
              <div className="flex items-center justify-between pt-1 border-t border-slate-100">
                <span className="text-xs text-slate-500">Макс. <span className="font-medium text-slate-700">{doc.max_up_per_day || 120}</span> УП/день</span>
                <button onClick={() => handleOpenModal(doc)} className="text-xs text-blue-600 hover:text-blue-800 font-medium transition-colors">
                  Редактировать
                </button>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Модальное окно добавления/редактирования врача */}
      {isModalOpen && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-end sm:items-center justify-center z-50 sm:p-4">
          <div className="bg-white sm:rounded-2xl shadow-2xl max-w-lg w-full max-h-[95vh] sm:max-h-[90vh] overflow-y-auto rounded-t-2xl">
            <div className="flex justify-between items-center p-5 border-b border-slate-200 sticky top-0 bg-white z-10">
              <h3 className="text-lg font-bold text-slate-900">
                {editingDoctor ? 'Редактировать врача' : 'Добавить врача'}
              </h3>
              <button
                onClick={handleCloseModal}
                className="text-slate-500 hover:text-slate-700 transition-colors p-1"
              >
                <X size={24} />
              </button>
            </div>

            <form onSubmit={handleSubmit} className="p-5 space-y-5">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1.5">
                  ФИО
                </label>
                <input
                  type="text"
                  value={formData.fio_alias}
                  onChange={(e) => setFormData({ ...formData, fio_alias: e.target.value })}
                  className="w-full px-4 py-2.5 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all"
                  required
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1.5">
                  Специализация
                </label>
                <select
                  value={formData.position_type}
                  onChange={(e) => setFormData({ ...formData, position_type: e.target.value })}
                  className="w-full px-4 py-2.5 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all"
                >
                  <option value="radiologist">Рентгенолог</option>
                  <option value="diagnostician">КТ-диагност</option>
                  <option value="other">Другое</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1.5">
                  Макс. УП/день
                </label>
                <input
                  type="number"
                  value={formData.max_up_per_day}
                  onChange={(e) => setFormData({ ...formData, max_up_per_day: Number(e.target.value) || 120 })}
                  className="w-full px-4 py-2.5 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all"
                  min="1"
                  required
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1.5">
                  Модальности (через запятую)
                </label>
                <input
                  type="text"
                  value={formData.modality.join(', ')}
                  onChange={(e) =>
                    setFormData({
                      ...formData,
                      modality: e.target.value
                        .split(',')
                        .map((m) => m.trim())
                        .filter(Boolean),
                    })
                  }
                  className="w-full px-4 py-2.5 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-all"
                  placeholder="КТ, МРТ, Рентген"
                />
              </div>

              <div className="flex items-center">
                <input
                  type="checkbox"
                  id="is_active"
                  checked={formData.is_active}
                  onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                  className="w-5 h-5 text-blue-600 border-slate-300 rounded focus:ring-blue-500"
                />
                <label htmlFor="is_active" className="ml-3 text-sm font-medium text-slate-700">
                  Активен
                </label>
              </div>

              <div className="flex gap-4 pt-6">
                <button
                  type="submit"
                  className="flex-1 px-6 py-3 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition-colors shadow-sm"
                >
                  {editingDoctor ? 'Сохранить изменения' : 'Добавить врача'}
                </button>
                <button
                  type="button"
                  onClick={handleCloseModal}
                  className="flex-1 px-6 py-3 bg-slate-100 text-slate-700 rounded-lg font-medium hover:bg-slate-200 transition-colors"
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