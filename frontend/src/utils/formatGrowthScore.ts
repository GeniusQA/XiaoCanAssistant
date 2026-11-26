export const formatGrowthScore = (value?: number | string | null): number => {
  const raw = Number(value || 0);
  if (!Number.isFinite(raw)) return 0;
  return Math.floor(raw / 100);
};
