'use client';

import { LocalizedText, useI18n } from '../i18n/provider';


import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useState } from 'react';
import { User, workspace } from '../paper-trading/types';

export default function AccountMenu() {
  const { t, locale } = useI18n();

  const pathname = usePathname();
  const [user, setUser] = useState<User | null>(null);
  const [csrf, setCsrf] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    setUser(null);setCsrf('');setError('');
    let sequence = 0;
    function check() {
      const current = ++sequence;
      void workspace<{ user: User; csrf_token: string }>('auth/me', { signal: controller.signal }).then(result => {if (!controller.signal.aborted && current === sequence) {setUser(result.user);setCsrf(result.csrf_token);}}).catch(() => {if (!controller.signal.aborted && current === sequence) {setUser(null);setCsrf('');}});
    }
    check();
    window.addEventListener('mri-auth-changed', check);
    window.addEventListener('focus', check);
    return () => {controller.abort();window.removeEventListener('mri-auth-changed', check);window.removeEventListener('focus', check);};
  }, [pathname]);
  async function logout() {
    setBusy(true);setError('');
    try {await workspace('auth/logout', { body: {}, csrf });setUser(null);setCsrf('');window.dispatchEvent(new Event('mri-auth-changed'));window.location.assign('/paper-trading');}
    catch (error) {setError(error instanceof Error ? error.message : 'Logout unavailable.');}
    finally {setBusy(false);}
  }
  if (!user) return <Link className="account-login" href="/paper-trading"><LocalizedText id="log_in_f7c400"/></Link>;
  return <details className="account-menu"><summary><LocalizedText id="account_85dfa3" after/><span><LocalizedText id={user.role === 'admin' ? 'account_role_admin' : 'account_role_user'}/></span></summary><div className="account-menu-panel"><p>{user.username || user.email || '—'}</p><nav aria-label={t("Account navigation")}><Link href="/paper-trading"><LocalizedText id="my_virtual_portfolio_8e2ab7"/></Link>{user.role === 'admin' && <Link href="/admin" aria-current={pathname === '/admin' ? 'page' : undefined}><LocalizedText id="admin_console_ba8b2a"/></Link>}</nav><button disabled={busy || !csrf} onClick={logout}><LocalizedText>{busy ? 'Logging out…' : 'Log out'}</LocalizedText></button>{error && <p role="alert"><LocalizedText>{error}</LocalizedText></p>}</div></details>;
}
