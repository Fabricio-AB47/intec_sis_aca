import { lazy, Suspense, useState } from 'react'
import { TitulacionView } from '../matricula/TitulacionView'
import './TitulationPortal.css'

const TitulationPortal = lazy(() => import('./TitulationPortal').then(module => ({ default: module.TitulationPortal })))

export function TitulationWorkspace({ displayName, role }: { displayName: string; role: string }) {
  const [view, setView] = useState<'individual' | 'portal'>('individual')
  return <div className="titulation-workspace">
    <div className="titulation-workspace__tabs" role="tablist" aria-label="Gestión de titulación">
      <button type="button" role="tab" aria-selected={view === 'individual'} onClick={() => setView('individual')}>Expediente individual</button>
      <button type="button" role="tab" aria-selected={view === 'portal'} onClick={() => setView('portal')}>Gestión integral</button>
    </div>
    <div hidden={view !== 'individual'}><TitulacionView displayName={displayName} role={role} section="proceso" /></div>
    {view === 'portal' && <Suspense fallback={<p role="status">Cargando titulación...</p>}><TitulationPortal /></Suspense>}
  </div>
}
