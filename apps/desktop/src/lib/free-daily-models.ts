/** Providers that give some models away every day, in the order Thoth lists them and rotates
 *  through them. Mirrors FREE_MODEL_PROVIDERS in hermes_cli/free_models.py. */
export const FREE_DAILY_MODEL_PROVIDERS: readonly string[] = ['cline', 'nous', 'openrouter', 'kilocode', 'opencode-zen']

export function hasFreeDailyModels(provider: null | string | undefined): boolean {
  return FREE_DAILY_MODEL_PROVIDERS.includes((provider ?? '').trim().toLowerCase())
}

/** Sort key: free-model providers first, in list order; everyone else after. */
export function freeDailyModelsRank(provider: null | string | undefined): number {
  const index = FREE_DAILY_MODEL_PROVIDERS.indexOf((provider ?? '').trim().toLowerCase())

  return index === -1 ? FREE_DAILY_MODEL_PROVIDERS.length : index
}
