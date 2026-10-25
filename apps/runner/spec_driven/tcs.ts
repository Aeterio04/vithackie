import type { TcImpl } from './lib';
import { NAV_TCS } from './tcs_nav';
import { HOME_TCS, FAQ_TCS } from './tcs_home';
import { PAGE_TCS } from './tcs_pages';

/** TC id -> implementation. A TC without an implementation fails loudly (script_error), never silently passes. */
export const TCS: Record<string, TcImpl> = { ...NAV_TCS, ...HOME_TCS, ...FAQ_TCS, ...PAGE_TCS };
