import { useId } from "react";

/**
 * Rafta mark: an "R" whose bowl is a parcel (the notch is the packing tape),
 * standing on a shelf. "Rafta" is Turkish for "on the shelf".
 */
export function LogoMark({ size = 24, title }: { size?: number; title?: string }) {
  const id = useId().replace(/:/g, "");
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" role={title ? "img" : undefined} aria-hidden={title ? undefined : true}>
      {title && <title>{title}</title>}
      <defs>
        <linearGradient id={`rafta-${id}`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#7d6ef2" />
          <stop offset="1" stopColor="#4a3bbd" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="8" fill={`url(#rafta-${id})`} />
      <path d="M9 6.5h10.5a3.5 3.5 0 0 1 3.5 3.5v3a3.5 3.5 0 0 1-3.5 3.5h-6.3v5.5H9z" fill="#fff" />
      <rect x="15.3" y="6.5" width="2.4" height="3.8" rx=".6" fill={`url(#rafta-${id})`} />
      <path d="M16 17.6l4.4 4.4" stroke="#fff" strokeWidth="4" strokeLinecap="round" />
      <rect x="6.5" y="24" width="19" height="2.6" rx="1.3" fill="#fff" fillOpacity=".9" />
    </svg>
  );
}
