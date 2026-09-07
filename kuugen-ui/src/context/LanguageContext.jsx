import { createContext, useState, useEffect, useMemo, useCallback } from 'react';
import { SUPPORTED_LANGUAGES, translations, DEFAULT_LANGUAGE } from '../locales';

export const LanguageContext = createContext(null);

export function LanguageProvider({ children }) {
  const [currentLang, setCurrentLang] = useState(() => {
    return localStorage.getItem('kuugen-lang') || DEFAULT_LANGUAGE;
  });

  useEffect(() => {
    localStorage.setItem('kuugen-lang', currentLang);
    document.documentElement.lang = currentLang;
  }, [currentLang]);

  // Helper to resolve nested keys like 'common.newChat'
  const getNestedValue = (obj, path) => {
    if (!obj || !path) return null;
    return path.split('.').reduce((prev, curr) => prev?.[curr], obj);
  };

  // Translation function with variable interpolation: t('status.executingSingle', { current: 1, total: 3 })
  const t = useCallback((key, params = {}) => {
    const activeDict = translations[currentLang] || translations[DEFAULT_LANGUAGE];
    const fallbackDict = translations[DEFAULT_LANGUAGE] || translations['en-US'];

    let template = getNestedValue(activeDict, key) ?? getNestedValue(fallbackDict, key) ?? key;

    if (typeof template !== 'string') return template;

    // Interpolate {paramName}
    return Object.entries(params).reduce((str, [k, v]) => {
      return str.replace(new RegExp(`\\{${k}\\}`, 'g'), v ?? '');
    }, template);
  }, [currentLang]);

  // Translate predefined step titles (memory, plan, finalize) or fallback to task description
  const translateStepTitle = useCallback((stepId, defaultTitle) => {
    if (stepId === 'memory') return t('step.memory');
    if (stepId === 'plan') return t('step.plan');
    if (stepId === 'finalize') return t('step.finalize');
    return defaultTitle;
  }, [t]);

  // Translate server progress message using stage key and stage_params
  const translateStatus = useCallback((statusMsg) => {
    if (!statusMsg) return '';
    if (statusMsg.stage) {
      const stageKey = `status.${statusMsg.stage}`;
      const translated = t(stageKey, statusMsg.stage_params || {});
      if (translated && translated !== stageKey) {
        return translated;
      }
    }
    return statusMsg.content || '';
  }, [t]);

  const value = useMemo(() => ({
    currentLang,
    setLanguage: setCurrentLang,
    languages: SUPPORTED_LANGUAGES,
    t,
    translateStepTitle,
    translateStatus
  }), [currentLang, t, translateStepTitle, translateStatus]);

  return (
    <LanguageContext.Provider value={value}>
      {children}
    </LanguageContext.Provider>
  );
}
