'use client';

import { LocalizedText } from '../i18n/provider';

import { FormEvent, useState } from 'react';
import { User, workspace } from './types';

export default function AccountPanel({ onAuthenticated }: { onAuthenticated: (user: User) => void }) {
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const email = String(form.get('email') || '').trim();
    const password = String(form.get('password') || '');
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) { setError('Enter a valid email address.'); return; }
    if (password.length < 10) { setError('String should have at least 10 characters'); return; }
    if (password.length > 128) { setError('String should have at most 128 characters'); return; }
    setBusy(true); setError('');
    try { const result = await workspace<{ user: User }>(`auth/${mode}`, { body: { email: form.get('email'), password: form.get('password') } }); onAuthenticated(result.user); window.dispatchEvent(new Event('mri-auth-changed')); }
    catch (error) { setError(error instanceof Error ? error.message : 'Account service unavailable.'); }
    finally { setBusy(false); }
  }
  return <section className="paper-account history-panel"><div><div className="eyebrow"><LocalizedText id="private_simulated_workspace_fd4f2f"/></div><h2><LocalizedText>{mode === 'login' ? 'Welcome back' : 'Create your virtual portfolio'}</LocalizedText></h2><p><LocalizedText id="independent_usd_and_krw_cash_accounts_whole_share_trades_complete_99a2fe"/></p><p><LocalizedText id="public_market_intelligence_remains_available_without_an_account_00b256"/></p></div><form onSubmit={submit} noValidate><div className="paper-segment"><button type="button" aria-pressed={mode === 'login'} onClick={() => {setMode('login');setError('');}}><LocalizedText id="log_in_f7c400"/></button><button type="button" aria-pressed={mode === 'register'} onClick={() => {setMode('register');setError('');}}><LocalizedText id="sign_up_0b8149"/></button></div><label><LocalizedText id="email_84add5"/><input name="email" type="email" autoComplete="username" required maxLength={254}/></label><label><LocalizedText id="password_8be3c9"/><input name="password" type="password" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} minLength={10} maxLength={128} required/></label><small><LocalizedText id="use_at_least_10_characters_no_real_money_or_brokerage_connection_e913db"/></small>{error && <p className="paper-error" role="alert"><LocalizedText>{error}</LocalizedText></p>}<button className="paper-primary" disabled={busy}><LocalizedText>{busy ? 'Connecting…' : mode === 'login' ? 'Log in' : 'Create account'}</LocalizedText></button></form></section>;
}
