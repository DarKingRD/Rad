import React from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';

interface PaginationProps {
  page: number;
  setPage: (page: number) => void;
  totalPages: number;
}

const Pagination: React.FC<PaginationProps> = ({ page, setPage, totalPages }) => {
  if (totalPages <= 1) return null;

  return (
    <div className="flex items-center justify-center gap-2">
      <button
        onClick={() => setPage(Math.max(1, page - 1))}
        disabled={page <= 1}
        className="inline-flex items-center gap-1 px-3 py-2 rounded-lg border border-slate-300 text-sm text-slate-700 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-slate-50"
      >
        <ChevronLeft size={16} />
        Назад
      </button>

      <span className="text-sm text-slate-600 px-2">
        Страница <span className="font-medium text-slate-900">{page}</span> из{' '}
        <span className="font-medium text-slate-900">{totalPages}</span>
      </span>

      <button
        onClick={() => setPage(Math.min(totalPages, page + 1))}
        disabled={page >= totalPages}
        className="inline-flex items-center gap-1 px-3 py-2 rounded-lg border border-slate-300 text-sm text-slate-700 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-slate-50"
      >
        Вперёд
        <ChevronRight size={16} />
      </button>
    </div>
  );
};

export default Pagination;