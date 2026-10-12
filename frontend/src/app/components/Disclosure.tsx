'use client';

import { LocalizedText } from '../i18n/provider';


import { ReactNode, useState } from 'react';

export default function Disclosure({ label, children, lazy = false }: { label: string; children: ReactNode; lazy?: boolean }) {
  const [open, setOpen] = useState(false);
  return <details className="research-disclosure" onToggle={event => setOpen(event.currentTarget.open)}><summary><LocalizedText>{label}</LocalizedText></summary><div className="disclosure-content"><LocalizedText>{!lazy || open ? children : null}</LocalizedText></div></details>;
}
