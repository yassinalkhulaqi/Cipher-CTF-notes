export interface Crumb {
  id: number;
  title: string;
}

interface BreadcrumbsProps {
  crumbs: Crumb[];
  current: string;
  onVault: () => void;
  onGoTo: (id: number) => void;
}

/** Vault / folder / … / current-note navigation trail. */
export function Breadcrumbs({
  crumbs,
  current,
  onVault,
  onGoTo,
}: BreadcrumbsProps) {
  return (
    <div className="breadcrumbs" aria-label="Breadcrumb">
      <button type="button" onClick={onVault}>
        Vault
      </button>
      {crumbs.map((crumb) => (
        <span key={crumb.id} style={{ display: "contents" }}>
          <span className="sep">/</span>
          <button
            type="button"
            onClick={() => onGoTo(crumb.id)}
            title={crumb.title}
          >
            {crumb.title}
          </button>
        </span>
      ))}
      <span className="sep">/</span>
      <span className="current">{current}</span>
    </div>
  );
}
