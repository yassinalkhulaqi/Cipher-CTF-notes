import { useMemo, useState, type ReactNode } from "react";
import { cx } from "../lib/ux";

export type SortDirection = "asc" | "desc";

export interface TableSort {
  key: string;
  direction: SortDirection;
}

export type SortValue = string | number | boolean | null | undefined;

export interface DataTableColumn<T> {
  key: string;
  header: ReactNode;
  render: (row: T, index: number) => ReactNode;
  sortable?: boolean;
  sortValue?: (row: T) => SortValue;
  align?: "left" | "center" | "right";
  width?: string;
  className?: string;
}

export interface DataTableProps<T> {
  columns: DataTableColumn<T>[];
  rows: T[];
  getRowKey: (row: T, index: number) => string | number;
  label: string;
  caption?: ReactNode;
  sort?: TableSort | null;
  defaultSort?: TableSort | null;
  onSortChange?: (sort: TableSort | null) => void;
  empty?: ReactNode;
  className?: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function fallbackValue(row: unknown, key: string): SortValue {
  if (!isRecord(row)) return "";
  const value = row[key];
  if (
    typeof value === "string" ||
    typeof value === "number" ||
    typeof value === "boolean" ||
    value === null ||
    value === undefined
  ) {
    return value;
  }
  return "";
}

function compareValues(left: SortValue, right: SortValue): number {
  if (typeof left === "number" && typeof right === "number") {
    return left - right;
  }
  return String(left ?? "").localeCompare(String(right ?? ""), undefined, {
    numeric: true,
    sensitivity: "base",
  });
}

export function DataTable<T>({
  columns,
  rows,
  getRowKey,
  label,
  caption,
  sort,
  defaultSort,
  onSortChange,
  empty,
  className,
}: DataTableProps<T>) {
  const [internalSort, setInternalSort] = useState<TableSort | null>(
    defaultSort ?? null,
  );
  const activeSort = sort !== undefined ? sort : internalSort;

  const sortedRows = useMemo(() => {
    if (!activeSort) return rows;
    const column = columns.find(
      (item) => item.key === activeSort.key && item.sortable,
    );
    if (!column) return rows;

    return rows
      .map((row, index) => ({
        row,
        index,
        value: column.sortValue
          ? column.sortValue(row)
          : fallbackValue(row, column.key),
      }))
      .sort((left, right) => {
        const result = compareValues(left.value, right.value);
        if (result !== 0) {
          return activeSort.direction === "asc" ? result : -result;
        }
        return left.index - right.index;
      })
      .map((entry) => entry.row);
  }, [activeSort, columns, rows]);

  const toggleSort = (column: DataTableColumn<T>) => {
    if (!column.sortable) return;
    const next: TableSort | null =
      activeSort?.key === column.key
        ? activeSort.direction === "asc"
          ? { key: column.key, direction: "desc" }
          : null
        : { key: column.key, direction: "asc" };

    if (sort === undefined) setInternalSort(next);
    onSortChange?.(next);
  };

  return (
    <div className={cx("ui-table-wrap", className)}>
      <table className="ui-table" aria-label={label}>
        {caption ? <caption>{caption}</caption> : null}
        <thead>
          <tr>
            {columns.map((column) => {
              const direction =
                activeSort?.key === column.key ? activeSort.direction : null;
              const ariaSort = !column.sortable
                ? undefined
                : direction
                  ? direction === "asc"
                    ? "ascending"
                    : "descending"
                  : "none";
              const indicator = !column.sortable
                ? null
                : direction
                  ? direction === "asc"
                    ? "↑"
                    : "↓"
                  : "↕";
              return (
                <th
                  key={column.key}
                  scope="col"
                  className={cx(
                    `ui-table__cell--${column.align ?? "left"}`,
                    column.className,
                  )}
                  style={column.width ? { width: column.width } : undefined}
                  aria-sort={ariaSort}
                >
                  {column.sortable ? (
                    <button
                      type="button"
                      className="ui-table__sort"
                      onClick={() => toggleSort(column)}
                    >
                      <span>{column.header}</span>
                      <span
                        className="ui-table__sort-indicator"
                        aria-hidden="true"
                      >
                        {indicator}
                      </span>
                    </button>
                  ) : (
                    column.header
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {sortedRows.length === 0 ? (
            <tr>
              <td
                className="ui-table__empty"
                colSpan={Math.max(1, columns.length)}
              >
                {empty ?? "No rows"}
              </td>
            </tr>
          ) : (
            sortedRows.map((row, index) => (
              <tr key={getRowKey(row, index)}>
                {columns.map((column) => (
                  <td
                    key={column.key}
                    className={cx(
                      `ui-table__cell--${column.align ?? "left"}`,
                      column.className,
                    )}
                  >
                    {column.render(row, index)}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
