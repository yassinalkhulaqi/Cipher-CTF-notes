import { useMemo, useState } from "react";
import { Button } from "../../ui/Button";
import { EmptyState } from "../../ui/EmptyState";
import { Field } from "../../ui/Field";
import { templateCategories } from "./helpers";
import type { TemplatePreview, TemplateRecord } from "./types";

export interface TemplatePickerProps {
  templates: TemplateRecord[];
  values: Record<string, unknown>;
  onRender: (key: string) => void;
  preview: TemplatePreview | null;
}

export function TemplatePicker({
  templates,
  values,
  onRender,
  preview,
}: TemplatePickerProps) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("");
  const categories = useMemo(() => templateCategories(templates), [templates]);
  const visible = useMemo(
    () =>
      templates.filter((template) => {
        if (category && template.category !== category) return false;
        if (!query.trim()) return true;
        const needle = query.trim().toLocaleLowerCase();
        return `${template.key} ${template.name} ${template.description} ${template.tags.join(" ")}`
          .toLocaleLowerCase()
          .includes(needle);
      }),
    [templates, query, category],
  );

  return (
    <section className="pb-templates" aria-label="Template picker">
      <div className="pb-snippets__filters">
        <Field
          label="Search templates"
          placeholder="report, checklist, finding"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <label className="pb-field">
          <span>Category</span>
          <select
            value={category}
            onChange={(event) => setCategory(event.target.value)}
          >
            <option value="">All categories</option>
            {categories.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
      </div>

      {templateValuesPreview(values)}

      {visible.length === 0 ? (
        <EmptyState
          title="No templates found"
          description="Try another query or category."
        />
      ) : (
        <div className="pb-template-grid">
          {visible.map((template) => (
            <article className="pb-template" key={template.key}>
              <header>
                <strong>{template.name}</strong>
                <code>{template.key}</code>
              </header>
              <p>{template.description || "No description"}</p>
              <div className="pb-template__meta">
                <span className="pb-chip pb-chip--muted">
                  {template.category}
                </span>
                <span className="pb-chip pb-chip--muted">
                  v{template.version}
                </span>
                {template.variables.slice(0, 4).map((definition) => (
                  <span className="pb-chip" key={definition.key}>
                    {definition.key}
                  </span>
                ))}
              </div>
              <Button
                size="sm"
                variant="secondary"
                onClick={() => onRender(template.key)}
              >
                Render preview
              </Button>
            </article>
          ))}
        </div>
      )}

      {preview ? (
        <div className="pb-template-preview">
          <header>
            <strong>{preview.key}</strong>
            <span>v{preview.version}</span>
          </header>
          {preview.unresolved.length > 0 ? (
            <p className="pb-warning">
              Unresolved: {preview.unresolved.join(", ")}
            </p>
          ) : null}
          <pre>{preview.content}</pre>
        </div>
      ) : null}
    </section>
  );
}

function templateValuesPreview(values: Record<string, unknown>) {
  const keys = Object.keys(values);
  if (keys.length === 0) return null;
  return (
    <div className="pb-template-values">
      <span>Active variables</span>
      <div className="pb-chip-row">
        {keys.map((key) => (
          <span className="pb-chip pb-chip--muted" key={key}>
            {key}
          </span>
        ))}
      </div>
    </div>
  );
}
