export function BrandMark({
  className = "brand-mark",
}: {
  className?: string;
}) {
  return (
    <span className={className} aria-hidden="true">
      <svg viewBox="0 0 64 64" fill="none">
        <rect width="64" height="64" rx="14" fill="currentColor" />
        <path
          d="M20 50V14h13.6c7.6 0 12.4 4 12.4 10.6 0 4.9-2.8 8.3-7.4 9.7L48 50h-9l-8.2-14.2H27.4V50H20zm7.4-20.6h5.2c3.6 0 5.8-1.9 5.8-4.8s-2.2-4.8-5.8-4.8h-5.2v9.6z"
          fill="var(--surface)"
        />
      </svg>
    </span>
  );
}
