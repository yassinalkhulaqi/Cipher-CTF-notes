import { blockPlainText, documentWordCount } from "./blocks";
import {
  BLOCK_LIMITS,
  type Block,
  type BlockDocument,
  type ValidationIssue,
  type ValidationReport,
} from "./types";

const CONTROL_RE = /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/;
const UNSAFE_SOURCE_RE = /^(javascript|data|vbscript):/i;

function issue(
  severity: ValidationIssue["severity"],
  code: string,
  message: string,
  block: Block | null = null,
  field = "",
): ValidationIssue {
  return { severity, code, message, blockId: block?.id ?? "", field };
}

export function validateBlock(block: Block): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  const text = blockPlainText(block);
  if (text.length > BLOCK_LIMITS.maxTextLength) {
    issues.push(
      issue("error", "text_too_long", "Block text is too long", block, "text"),
    );
  }
  if (CONTROL_RE.test(text)) {
    issues.push(
      issue(
        "error",
        "control_characters",
        "Text has control characters",
        block,
        "text",
      ),
    );
  }
  if (block.type === "heading") {
    if (block.level < 1 || block.level > BLOCK_LIMITS.maxHeadingLevel) {
      issues.push(
        issue(
          "error",
          "invalid_heading_level",
          "Heading level is out of range",
          block,
          "level",
        ),
      );
    }
    if (!block.text.trim()) {
      issues.push(
        issue("warning", "empty_heading", "Heading has no text", block, "text"),
      );
    }
  }
  if (block.type === "code") {
    if (!block.text.trim()) {
      issues.push(
        issue("warning", "empty_code", "Code block is empty", block, "text"),
      );
    }
    if (/[\s)]/.test(block.language)) {
      issues.push(
        issue(
          "error",
          "invalid_language",
          "Invalid code language",
          block,
          "language",
        ),
      );
    }
  }
  if (block.type === "list") {
    if (block.items.length === 0) {
      issues.push(
        issue("error", "empty_list", "List has no items", block, "items"),
      );
    }
    if (block.items.length > BLOCK_LIMITS.maxItems) {
      issues.push(
        issue(
          "error",
          "too_many_items",
          "List has too many items",
          block,
          "items",
        ),
      );
    }
    if (
      block.style === "tasks" &&
      block.checked.length !== block.items.length
    ) {
      issues.push(
        issue(
          "error",
          "checkbox_mismatch",
          "Checkboxes do not match items",
          block,
          "checked",
        ),
      );
    }
    block.items.forEach((item, index) => {
      if (!item.trim()) {
        issues.push(
          issue(
            "warning",
            "empty_list_item",
            `Item ${index + 1} is empty`,
            block,
            "items",
          ),
        );
      }
      if (item.length > BLOCK_LIMITS.maxItemLength) {
        issues.push(
          issue(
            "error",
            "item_too_long",
            `Item ${index + 1} is too long`,
            block,
            "items",
          ),
        );
      }
    });
  }
  if (block.type === "table") {
    if (block.headers.length === 0) {
      issues.push(
        issue("error", "empty_table", "Table has no headers", block, "headers"),
      );
    }
    if (block.headers.length > BLOCK_LIMITS.maxTableColumns) {
      issues.push(
        issue(
          "error",
          "too_many_columns",
          "Table has too many columns",
          block,
          "headers",
        ),
      );
    }
    block.rows.forEach((row, index) => {
      if (row.length !== block.headers.length) {
        issues.push(
          issue(
            "error",
            "ragged_table",
            `Row ${index + 1} has an unexpected width`,
            block,
            "rows",
          ),
        );
      }
    });
  }
  if (block.type === "image") {
    if (!block.source) {
      issues.push(
        issue(
          "error",
          "missing_source",
          "Image needs a source",
          block,
          "source",
        ),
      );
    } else if (UNSAFE_SOURCE_RE.test(block.source)) {
      issues.push(
        issue(
          "error",
          "unsafe_source",
          "Image source uses an unsafe scheme",
          block,
          "source",
        ),
      );
    }
    if (!block.alt.trim()) {
      issues.push(
        issue("warning", "missing_alt", "Image has no alt text", block, "alt"),
      );
    }
  }
  const seenMentions = new Set<string>();
  for (const mention of block.mentions) {
    const key = `${mention.kind}:${mention.target}`;
    if (seenMentions.has(key)) {
      issues.push(
        issue(
          "warning",
          "duplicate_mention",
          `Duplicate mention ${mention.target}`,
          block,
          "mentions",
        ),
      );
    }
    seenMentions.add(key);
    if (mention.end > block.text.length || mention.end <= mention.start) {
      issues.push(
        issue(
          "error",
          "mention_offsets",
          "Mention offsets are invalid",
          block,
          "mentions",
        ),
      );
    }
  }
  return issues;
}

export function validateDocument(document: BlockDocument): ValidationReport {
  const issues: ValidationIssue[] = [];
  if (!document.id.trim()) {
    issues.push(issue("error", "missing_id", "Document id is required"));
  }
  if (document.title.length > 300) {
    issues.push(
      issue(
        "error",
        "title_too_long",
        "Document title is too long",
        null,
        "title",
      ),
    );
  }
  if (document.blocks.length === 0) {
    issues.push(
      issue("error", "no_blocks", "Document has no blocks", null, "blocks"),
    );
  }
  if (document.blocks.length > BLOCK_LIMITS.maxBlocks) {
    issues.push(
      issue(
        "error",
        "too_many_blocks",
        "Document has too many blocks",
        null,
        "blocks",
      ),
    );
  }
  if (document.revision < 0) {
    issues.push(
      issue(
        "error",
        "negative_revision",
        "Revision cannot be negative",
        null,
        "revision",
      ),
    );
  }
  const seen = new Set<string>();
  for (const block of document.blocks) {
    if (seen.has(block.id)) {
      issues.push(
        issue(
          "error",
          "duplicate_block_id",
          `Duplicate block id ${block.id}`,
          block,
          "id",
        ),
      );
    }
    seen.add(block.id);
    issues.push(...validateBlock(block));
  }
  return summarizeReport(document.id, issues);
}

export function summarizeReport(
  target: string,
  issues: ValidationIssue[],
): ValidationReport {
  const errors = issues.filter((item) => item.severity === "error").length;
  const warnings = issues.filter((item) => item.severity === "warning").length;
  return { target, ok: errors === 0, errors, warnings, issues };
}

export function issuesForBlock(
  report: ValidationReport,
  blockId: string,
): ValidationIssue[] {
  return report.issues.filter((item) => item.blockId === blockId);
}

export function firstError(report: ValidationReport): ValidationIssue | null {
  return report.issues.find((item) => item.severity === "error") ?? null;
}

export function hasIssue(report: ValidationReport, code: string): boolean {
  return report.issues.some((item) => item.code === code);
}

export function validationMessage(report: ValidationReport): string {
  if (report.ok) return "Document is valid";
  const first = firstError(report);
  return first ? first.message : "Document has warnings";
}

export function documentStats(document: BlockDocument): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const block of document.blocks)
    counts[block.type] = (counts[block.type] ?? 0) + 1;
  return {
    blocks: document.blocks.length,
    words: documentWordCount(document),
    headings: counts.heading ?? 0,
    code: counts.code ?? 0,
    lists: counts.list ?? 0,
    tables: counts.table ?? 0,
  };
}
