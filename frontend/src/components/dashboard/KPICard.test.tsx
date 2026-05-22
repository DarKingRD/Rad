import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { KPICard } from './KPICard';

describe('KPICard', () => {
  it('renders title, value and subtext', () => {
    render(<KPICard title="Всего исследований" value={128} subtext="за выбранный период" />);

    expect(screen.getByText('Всего исследований')).toBeInTheDocument();
    expect(screen.getByText('128')).toBeInTheDocument();
    expect(screen.getByText('за выбранный период')).toBeInTheDocument();
  });

  it('formats positive trend with a plus sign', () => {
    render(<KPICard title="Выполнено" value="72%" subtext="к прошлой неделе" trend={12} />);

    expect(screen.getByText('+12%')).toBeInTheDocument();
  });

  it('does not render trend badge for zero trend', () => {
    render(<KPICard title="Очередь" value={0} subtext="нет изменений" trend={0} />);

    expect(screen.queryByText('0%')).not.toBeInTheDocument();
  });
});
