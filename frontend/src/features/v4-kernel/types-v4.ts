export interface PageMetaV4 {
  request_id: string;
  version: string;
  page: number;
  page_size: number;
  etag?: string;
  next_cursor?: string;
}

export interface V4Envelope<T> {
  data: T;
  meta: PageMetaV4;
}

export interface V4ErrorDetail {
  code: string;
  message: string;
  details: string[];
}

export interface V4Error {
  error: V4ErrorDetail;
}

export type V4RouteName =
  | "inbox"
  | "findings"
  | "evidence-lab"
  | "blocks-pro"
  | "query"
  | "automation"
  | "report-designer"
  | "graph-workbench"
  | "security-vault"
  | "a11y-i18n";

export interface V4Route {
  name: V4RouteName;
  label: string;
  path: string;
  shortcut?: string;
  icon?: string;
}

export interface V4Preference {
  theme: "light" | "graphite" | "system";
  density: "compact" | "default" | "comfortable";
  motion: "full" | "subtle" | "off";
  locale: string;
  direction: "ltr" | "rtl";
}
