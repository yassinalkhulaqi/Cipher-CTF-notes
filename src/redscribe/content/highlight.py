"""A small, dependency-free syntax highlighter for fenced code blocks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True, slots=True)
class CodeToken:
    kind: str
    text: str


_LANGUAGE_ALIASES: dict[str, str] = {
    "py": "python",
    "python3": "python",
    "sh": "bash",
    "shell": "bash",
    "zsh": "bash",
    "console": "bash",
    "ps1": "powershell",
    "pwsh": "powershell",
    "js": "javascript",
    "jsx": "javascript",
    "node": "javascript",
    "ts": "typescript",
    "tsx": "typescript",
    "c++": "cpp",
    "cxx": "cpp",
    "h": "c",
    "hpp": "cpp",
    "golang": "go",
    "rs": "rust",
    "yml": "yaml",
    "jsonc": "json",
    "postgres": "sql",
    "mysql": "sql",
    "sqlite": "sql",
    "http": "http",
    "https": "http",
    "txt": "text",
    "": "text",
}

_KEYWORDS: dict[str, frozenset[str]] = {
    "python": frozenset(
        "and as assert async await break case class continue def del elif else except finally for "
        "from global if import in is lambda match nonlocal not or pass raise return try while with "
        "yield".split()
    ),
    "bash": frozenset(
        "if then else elif fi for while until do done case esac in function select time coproc "
        "export local readonly declare unset shift source eval exec exit return break continue".split()
    ),
    "powershell": frozenset(
        "if else elseif foreach for while do until switch function param begin process end try "
        "catch finally throw return trap break continue in".split()
    ),
    "javascript": frozenset(
        "const let var function return if else for while do switch case break continue class extends "
        "new this typeof instanceof in of async await try catch finally throw import export from "
        "default delete void yield static get set".split()
    ),
    "typescript": frozenset(
        "const let var function return if else for while do switch case break continue class extends "
        "new this typeof instanceof in of async await try catch finally throw import export from "
        "default delete void yield static get set interface type enum implements public private "
        "protected readonly namespace declare as satisfies abstract keyof infer is".split()
    ),
    "sql": frozenset(
        "select from where join inner left right full outer on group by order having limit offset "
        "insert into values update set delete create table drop alter index view and or not null is "
        "as distinct union all case when then else end exists in like between primary key foreign "
        "references unique constraint default database schema begin commit rollback".split()
    ),
    "c": frozenset(
        "auto break case char const continue default do double else enum extern float for goto if "
        "inline int long register restrict return short signed sizeof static struct switch typedef "
        "union unsigned void volatile while".split()
    ),
    "cpp": frozenset(
        "auto break case char const constexpr continue default delete do double else enum extern "
        "float for goto if inline int long namespace new nullptr operator override private protected "
        "public register return short signed sizeof static struct switch template this throw try "
        "typedef typename union unsigned using virtual void volatile while class".split()
    ),
    "go": frozenset(
        "break case chan const continue default defer else fallthrough for func go goto if import "
        "interface map package range return select struct switch type var".split()
    ),
    "rust": frozenset(
        "as async await break const continue crate dyn else enum extern false fn for if impl in let "
        "loop match mod move mut pub ref return self static struct super trait true type unsafe use "
        "where while".split()
    ),
    "php": frozenset(
        "abstract and array as break callable case catch class clone const continue declare default "
        "do echo else elseif empty enddeclare endfor endforeach endif endswitch endwhile eval exit "
        "extends final finally fn for foreach function global goto if implements include include_once "
        "instanceof insteadof interface isset list match namespace new or print private protected "
        "public readonly require require_once return static switch throw trait try unset use var "
        "while xor yield".split()
    ),
    "ruby": frozenset(
        "alias and begin break case class def defined do else elsif end ensure false for if in module "
        "next nil not or redo rescue retry return self super then true undef unless until when while "
        "yield".split()
    ),
    "json": frozenset("true false null".split()),
    "yaml": frozenset("true false null yes no on off".split()),
    "http": frozenset(
        "get post put patch delete head options connect trace host user-agent accept".split()
    ),
}

_BUILTINS: dict[str, frozenset[str]] = {
    "python": frozenset(
        "true false none self cls print len range open int str bytes float bool list dict set tuple "
        "enumerate zip sum min max sorted reversed super isinstance issubclass getattr setattr "
        "hasattr type repr input format map filter any all".split()
    ),
    "bash": frozenset(
        "echo cd pwd ls cat grep sed awk cut sort uniq head tail chmod chown curl wget nc ncat "
        "python python3 pip git docker nmap ffuf gobuster nikto sqlmap hydra sudo su".split()
    ),
    "powershell": frozenset(
        "true false null write-host get-childitem get-content set-content select-object where-object "
        "foreach-object invoke-webrequest invoke-expression start-process stop-process".split()
    ),
    "javascript": frozenset(
        "true false null undefined console document window require module process fetch promise "
        "array object string number boolean json math".split()
    ),
    "typescript": frozenset(
        "true false null undefined console document window require module process fetch promise "
        "array object string number boolean json math".split()
    ),
    "sql": frozenset(
        "count sum avg min max coalesce cast lower upper substr length now date".split()
    ),
    "c": frozenset(
        "printf fprintf sprintf snprintf scanf malloc calloc realloc free memcpy memset strlen strcpy "
        "strncpy strcmp fopen fclose fgets fread fwrite".split()
    ),
    "cpp": frozenset(
        "printf cout cin cerr endl malloc free memcpy memset strlen string vector map set unique_ptr "
        "shared_ptr make_unique make_shared".split()
    ),
    "go": frozenset("fmt len make new append cap copy delete panic recover print println".split()),
    "rust": frozenset("println print format vec some none ok err string vec option result".split()),
    "php": frozenset(
        "true false null strlen count array_map array_filter strpos preg_match isset unset echo".split()
    ),
    "ruby": frozenset("puts print require attr_accessor true false nil".split()),
    "json": frozenset(),
    "yaml": frozenset(),
    "http": frozenset(),
}

_COMMENT_PATTERN: dict[str, str] = {
    "python": r"#[^\n]*",
    "bash": r"#[^\n]*",
    "powershell": r"#[^\n]*",
    "ruby": r"#[^\n]*",
    "yaml": r"#[^\n]*",
    "javascript": r"//[^\n]*|/\*.*?\*/",
    "typescript": r"//[^\n]*|/\*.*?\*/",
    "c": r"//[^\n]*|/\*.*?\*/",
    "cpp": r"//[^\n]*|/\*.*?\*/",
    "go": r"//[^\n]*|/\*.*?\*/",
    "rust": r"//[^\n]*|/\*.*?\*/",
    "php": r"//[^\n]*|/\*.*?\*/|#[^\n]*",
    "sql": r"--[^\n]*|/\*.*?\*/",
    "json": "",
    "http": r"#[^\n]*",
}

_STRING_PATTERN = r""""(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`"""
_PYTHON_TRIPLE_DOUBLE = r'"""(?:\\.|(?!""").)*"""'
_PYTHON_TRIPLE_SINGLE = r"'''(?:\\.|(?!''').)*'''"
_PYTHON_TRIPLE_QUOTE = f"(?s:{_PYTHON_TRIPLE_DOUBLE}|{_PYTHON_TRIPLE_SINGLE})"
_VARIABLE_PATTERN = r"\$\{[^}\n]+\}|\$[A-Za-z_][A-Za-z0-9_]*|\$[0-9@*#?$!-]"
_NUMBER_PATTERN = r"\b(?:0x[0-9a-fA-F]+|\d+(?:\.\d+)?)\b"
_WORD_PATTERN = r"[A-Za-z_][A-Za-z0-9_-]*"
_CMDLET_PATTERN = re.compile(r"^[A-Z][a-z]+-[A-Z][A-Za-z]+$")


def normalize_language(language: str) -> str:
    cleaned = language.strip().lower().lstrip(".")
    return _LANGUAGE_ALIASES.get(cleaned, cleaned)


def tokenize_code(code: str, language: str = "") -> list[CodeToken]:
    """Split code into colored tokens while preserving every character."""
    lang = normalize_language(language)
    if not code:
        return []
    if lang not in _KEYWORDS:
        return [CodeToken("text", code)]

    master = _master_pattern(lang)
    tokens: list[CodeToken] = []
    position = 0
    for match in master.finditer(code):
        if match.start() > position:
            tokens.append(CodeToken("text", code[position : match.start()]))
        value = match.group(0)
        tokens.append(CodeToken(_classify(value, lang), value))
        position = match.end()
    if position < len(code):
        tokens.append(CodeToken("text", code[position:]))
    return _coalesce(tokens)


@lru_cache(maxsize=32)
def _master_pattern(lang: str) -> re.Pattern[str]:
    pieces: list[str] = []
    if lang == "python":
        pieces.append(_PYTHON_TRIPLE_QUOTE)
    pieces.append(_STRING_PATTERN)
    comment = _COMMENT_PATTERN.get(lang, "")
    if comment:
        pieces.append(comment)
    if lang in {"bash", "powershell", "php"}:
        pieces.append(_VARIABLE_PATTERN)
    pieces.extend((_NUMBER_PATTERN, _WORD_PATTERN))
    return re.compile("|".join(f"(?:{piece})" for piece in pieces), re.DOTALL)


def _classify(value: str, lang: str) -> str:
    if _is_string(value):
        return "string"
    if _is_comment(value, lang):
        return "comment"
    if value.startswith("$"):
        return "variable"
    if value[0].isdigit():
        return "number"
    lowered = value.lower()
    if lowered in _KEYWORDS[lang]:
        return "keyword"
    if lowered in _BUILTINS[lang] or (lang == "powershell" and _CMDLET_PATTERN.match(value)):
        return "builtin"
    return "text"


def _is_string(value: str) -> bool:
    return len(value) >= 2 and value[0] in {'"', "'", "`"} and value[-1] == value[0]


def _is_comment(value: str, lang: str) -> bool:
    if value.startswith(("#", "//", "--", "/*")):
        return True
    return lang == "sql" and value.startswith("--")


def _coalesce(tokens: list[CodeToken]) -> list[CodeToken]:
    merged: list[CodeToken] = []
    for token in tokens:
        if merged and merged[-1].kind == token.kind:
            merged[-1] = CodeToken(token.kind, merged[-1].text + token.text)
        else:
            merged.append(token)
    return merged
