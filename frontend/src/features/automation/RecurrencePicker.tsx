/** Recurrence picker with a live human-readable preview. */

import { formatOccurrence, humanize, validateRule } from "./recurrence";
import type { Frequency, RecurrenceRule } from "./types";
import { WEEKDAY_LABELS } from "./types";

export interface RecurrencePickerProps {
  rule: RecurrenceRule;
  occurrences: number[];
  onChange: (changes: Partial<RecurrenceRule>) => void;
  onPreview: () => void;
}

const FREQUENCIES: Frequency[] = ["hourly", "daily", "weekly", "monthly"];

export function RecurrencePicker({ rule, occurrences, onChange, onPreview }: RecurrencePickerProps) {
  const problems = validateRule(rule);
  return (
    <div className="automation-recurrence" data-automation="recurrence-picker">
      <div className="automation-recurrence__row">
        <label htmlFor="automation-frequency">Frequency</label>
        <select
          id="automation-frequency"
          data-automation="recurrence-frequency"
          value={rule.frequency}
          onChange={(event) => onChange({ frequency: event.target.value as Frequency })}
        >
          {FREQUENCIES.map((frequency) => (
            <option key={frequency} value={frequency}>
              {frequency}
            </option>
          ))}
        </select>
        <label htmlFor="automation-interval">Every</label>
        <input
          id="automation-interval"
          data-automation="recurrence-interval"
          type="number"
          min={1}
          value={rule.interval}
          onChange={(event) => onChange({ interval: Number(event.target.value) })}
        />
      </div>
      {rule.frequency === "weekly" && (
        <fieldset className="automation-recurrence__weekdays">
          <legend>Days</legend>
          {WEEKDAY_LABELS.map((label, index) => {
            const selected = (rule.by_weekday ?? []).includes(index);
            return (
              <label key={label}>
                <input
                  type="checkbox"
                  data-automation="recurrence-weekday"
                  data-day={index}
                  checked={selected}
                  onChange={() =>
                    onChange({
                      by_weekday: selected
                        ? (rule.by_weekday ?? []).filter((day) => day !== index)
                        : [...(rule.by_weekday ?? []), index].sort(),
                    })
                  }
                />
                {label}
              </label>
            );
          })}
        </fieldset>
      )}
      {rule.frequency === "monthly" && (
        <div className="automation-recurrence__row">
          <label htmlFor="automation-month-day">Day of month</label>
          <input
            id="automation-month-day"
            type="number"
            min={1}
            max={31}
            data-automation="recurrence-month-day"
            value={rule.by_month_day ?? 1}
            onChange={(event) => onChange({ by_month_day: Number(event.target.value) })}
          />
        </div>
      )}
      <div className="automation-recurrence__row">
        <label htmlFor="automation-hour">UTC time</label>
        <input
          id="automation-hour"
          type="number"
          min={0}
          max={23}
          data-automation="recurrence-hour"
          value={rule.hour}
          onChange={(event) => onChange({ hour: Number(event.target.value) })}
        />
        <span aria-hidden="true">:</span>
        <input
          aria-label="Minute"
          type="number"
          min={0}
          max={59}
          data-automation="recurrence-minute"
          value={rule.minute}
          onChange={(event) => onChange({ minute: Number(event.target.value) })}
        />
        <button type="button" data-automation="recurrence-preview" onClick={onPreview}>
          Preview
        </button>
      </div>
      <p className="automation-recurrence__description" data-automation="recurrence-description">
        {humanize(rule)}
      </p>
      {problems.map((problem) => (
        <p key={problem.code} className="automation-recurrence__problem" data-severity={problem.severity}>
          {problem.message}
        </p>
      ))}
      <ul className="automation-recurrence__occurrences" data-automation="recurrence-occurrences">
        {occurrences.map((timestamp) => (
          <li key={timestamp}>{formatOccurrence(timestamp)}</li>
        ))}
      </ul>
    </div>
  );
}
