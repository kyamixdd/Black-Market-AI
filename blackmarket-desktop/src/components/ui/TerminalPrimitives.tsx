import { Children } from 'react'
import type { ReactNode } from 'react'

export function ScreenHeader({ title, description, actions }: { title: string; description: string; actions?: ReactNode }) {
  return <div className="workspace-header"><div><h1>{title}</h1><p>{description}</p></div>{actions && <div className="workspace-actions">{actions}</div>}</div>
}

export function SummaryCard({ label, value, detail, tone }: { label: string; value: string; detail?: string; tone?: string }) {
  return <div className="workspace-summary-card"><span>{label}</span><strong className={tone}>{value}</strong>{detail && <small>{detail}</small>}</div>
}

export function EmptyState({ text }: { text: string }) {
  return <div className="workspace-empty" role="status">{text}</div>
}

export function DetailCard({ label, value }: { label: string; value: string }) {
  return <div className="workspace-detail"><span>{label}</span><b>{value}</b></div>
}

export function DataTable({ children, minWidth = 720 }: { children: ReactNode; minWidth?: number }) {
  const [header, ...rows] = Children.toArray(children)
  return <div className="workspace-table-wrap"><table style={{ minWidth }}><thead>{header}</thead><tbody>{rows}</tbody></table></div>
}

export function TableHead({ labels }: { labels: string[] }) {
  return <tr>{labels.map((label) => <th key={label}>{label}</th>)}</tr>
}
