'use client';

import { Globe2 } from 'lucide-react';
import { cloneElement, createContext, isValidElement, ReactElement, ReactNode, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { Language, languageCookie, localeCodes, MessageKey, message, translateText } from './messages';
interface Context { language: Language; locale: string; setLanguage: (language: Language) => void; t: (source: string) => string }
const I18nContext = createContext<Context>({language:'en',locale:'en-US',setLanguage:()=>{},t:source=>source});
function presentation(language: Language, source: string) {
  return translateText(language, source).replace(/\b(\d{4}-\d{2}-\d{2})\b(?!T)/g, date => {
    const parsed = new Date(`${date}T00:00:00Z`);
    return Number.isNaN(parsed.getTime()) ? date : new Intl.DateTimeFormat(localeCodes[language], {year:'numeric',month:'long',day:'numeric',timeZone:'UTC'}).format(parsed);
  });
}
export function I18nProvider({ initialLanguage, children }: { initialLanguage: Language; children: ReactNode }) {
  const [language,setLanguage] = useState<Language>(initialLanguage);
  useEffect(() => {
    document.documentElement.lang=language;
    document.cookie=`${languageCookie}=${language}; Path=/; Max-Age=31536000; SameSite=Lax${location.protocol==='https:'?'; Secure':''}`;
    document.title=`${translateText(language,'MARKET RISK INTELLIGENCE')} | ${translateText(language,'AI EARLY WARNING SYSTEM')}`;
  },[language]);
  const value = useMemo(()=>({language,locale:localeCodes[language],setLanguage,t:(source:string)=>presentation(language,source)}),[language]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}
export function useI18n() { return useContext(I18nContext); }
export function LocalizedText({ id, children, before = false, after = false }: { id?: MessageKey; children?: ReactNode; before?: boolean; after?: boolean }) {
  const {language,t}=useI18n();
  function render(node: ReactNode): ReactNode {
    if (typeof node==='string') return t(node);
    if (Array.isArray(node)) return node.map(render);
    if (isValidElement(node) && typeof node.type==='string') {
      const element=node as ReactElement<{children?:ReactNode}>;
      return cloneElement(element,{},render(element.props.children));
    }
    return node;
  }
  return <>{before?' ':''}{id?message(language,id):render(children)}{after?' ':''}</>;
}
const languageOptions: ReadonlyArray<{ code: Language; label: string; flag: string }> = [
  { code: 'en', label: 'English', flag: '🇺🇸' },
  { code: 'ko', label: '한국어', flag: '🇰🇷' },
];
export function LanguageSwitcher() {
  const {language,setLanguage,t}=useI18n();
  const dropdown=useRef<HTMLDetailsElement>(null);
  const trigger=useRef<HTMLElement>(null);
  const active=languageOptions.find(option=>option.code===language)!;
  useEffect(()=>{
    function outside(event: PointerEvent) {
      if (event.target instanceof Node && !dropdown.current?.contains(event.target) && dropdown.current) dropdown.current.open=false;
    }
    document.addEventListener('pointerdown',outside);
    return ()=>document.removeEventListener('pointerdown',outside);
  },[]);
  function close() {
    if (dropdown.current) dropdown.current.open=false;
    trigger.current?.focus();
  }
  return <details className="language-switcher" ref={dropdown} onKeyDown={event=>{if(event.key==='Escape'){event.preventDefault();close();}}}>
    <summary ref={trigger} aria-label={t('Interface language')}><Globe2 size={13} aria-hidden="true"/><span lang={active.code}>{active.label}</span><span className="language-chevron" aria-hidden="true">▼</span></summary>
    <div className="language-options" role="group" aria-label={t('Interface language')}>
      {languageOptions.map(option=><button key={option.code} type="button" lang={option.code} aria-pressed={language===option.code} onClick={()=>{setLanguage(option.code);close();}}><span aria-hidden="true">{option.flag}</span><span>{option.label}</span><span className="language-check" aria-hidden="true">{language===option.code?'✓':''}</span></button>)}
    </div>
  </details>;
}
