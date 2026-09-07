import zhTW from './zh-TW.json';
import enUS from './en-US.json';

export const SUPPORTED_LANGUAGES = [
  { code: 'zh-TW', label: '繁體中文', icon: '🇹🇼' },
  { code: 'en-US', label: 'English', icon: '🇺🇸' }
];

export const translations = {
  'zh-TW': zhTW,
  'en-US': enUS
};

export const DEFAULT_LANGUAGE = 'zh-TW';
