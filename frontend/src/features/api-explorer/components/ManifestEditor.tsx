/** Manifest editor with live, data-only schema validation. */

import { useMemo, useState } from "react";

import { createApiExplorerClient, type ApiExplorerClient } from "../client";
import { exampleManifestText, issueSummary } from "../pure";
import { useApiExplorerStore } from "../store";
import type { ManifestSchemaInfo } from "../types";

interface Props {
  client?: ApiExplorerClient;
}

export function ManifestEditor({ client }: Props) {
  const explorer = useMemo(() => client ?? createApiExplorerClient(), [client]);
  const manifestText = useApiExplorerStore((state) => state.manifestText);
  const report = useApiExplorerStore((state) => state.report);
  const setManifestText = useApiExplorerStore((state) => state.setManifestText);
  const validateLocal = useApiExplorerStore((state) => state.validateLocal);
  const setReport = useApiExplorerStore((state) => state.setReport);
  const [schema, setSchema] = useState<ManifestSchemaInfo | null>(null);
  const [remoteValid, setRemoteValid] = useState<boolean | null>(null);

  async function validateRemote() {
    let parsed: unknown;
    try {
      parsed = JSON.parse(manifestText);
    } catch {
      setRemoteValid(false);
      return;
    }
    try {
      const result = await explorer.validate(parsed);
      setReport(result);
      setRemoteValid(result.valid);
    } catch {
      setRemoteValid(false);
    }
  }

  return (
    <section
      className="api-explorer-panel manifest-editor"
      aria-label="Manifest editor"
    >
      <header className="api-explorer-panel__header">
        <div>
          <h2>Extension Manifest Editor</h2>
          <p>
            Contributions are data only. The app never executes manifest
            content.
          </p>
        </div>
        <span className="api-explorer__mode" data-write="false">
          data only
        </span>
      </header>

      <div className="manifest-editor__grid">
        <label className="api-explorer__wide">
          Manifest JSON
          <textarea
            className="manifest-editor__source"
            value={manifestText}
            onChange={(event) => {
              setManifestText(event.target.value);
              setRemoteValid(null);
            }}
            rows={18}
            spellCheck={false}
            placeholder={exampleManifestText().slice(0, 120)}
            aria-label="Manifest JSON"
          />
        </label>

        <div className="manifest-editor__validation">
          <div className="api-explorer__actions">
            <button type="button" onClick={() => validateLocal()}>
              Validate locally
            </button>
            <button type="button" onClick={() => void validateRemote()}>
              Validate via API
            </button>
            <button
              type="button"
              onClick={() => {
                setManifestText(exampleManifestText());
                setRemoteValid(null);
              }}
            >
              Load example
            </button>
            <button
              type="button"
              onClick={() => {
                void explorer
                  .schema()
                  .then(setSchema)
                  .catch(() => setSchema(null));
              }}
            >
              Load schema
            </button>
          </div>

          {report && (
            <div className="manifest-editor__report" data-valid={report.valid}>
              <strong>
                {report.valid ? "Valid declaration" : "Validation failed"}
              </strong>
              <p>{issueSummary(report)}</p>
              {report.fingerprint && (
                <p className="manifest-editor__fingerprint">
                  fingerprint <code>{report.fingerprint}</code>
                </p>
              )}
              <ul className="manifest-editor__issues">
                {report.issues.map((item, index) => (
                  <li
                    key={`${item.path}-${index}`}
                    data-severity={item.severity}
                  >
                    <code>{item.path}</code>
                    <span>{item.message}</span>
                  </li>
                ))}
              </ul>
              {report.normalized && (
                <p className="manifest-editor__count">
                  {report.normalized.contributions.length} contribution(s) ·{" "}
                  {report.normalized.requires.length} capability requirement(s)
                </p>
              )}
            </div>
          )}
          {remoteValid !== null && (
            <p className="manifest-editor__remote" data-valid={remoteValid}>
              API validation: {remoteValid ? "passed" : "failed"}
            </p>
          )}

          {schema && (
            <div className="manifest-editor__schema">
              <h3>Schema</h3>
              <p>
                {schema.schema_id} ·{" "}
                {Object.keys(schema.contribution_kinds).length} contribution
                kinds · {schema.forbidden_keys.length} forbidden keys
              </p>
              <p>executes_code: {String(schema.executes_code)}</p>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
