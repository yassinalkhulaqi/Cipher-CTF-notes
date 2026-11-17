"""A small, dependency-free syntax highlighter for fenced code blocks."""

from __future__ import annotations

import re
from dataclasses import dataclass

_EMPTY_FROZENSET: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class CodeToken:
    kind: str
    text: str


@dataclass(frozen=True, slots=True)
class LanguageSpec:
    keywords: frozenset[str]
    builtins: frozenset[str]
    line_comments: tuple[str, ...] = ()
    block_comments: tuple[tuple[str, str, bool], ...] = ()
    quotes: tuple[str, ...] = ('"', "'", "`")
    triples: tuple[str, ...] = ()
    prefixes: frozenset[str] = _EMPTY_FROZENSET
    raw_prefixes: frozenset[str] = _EMPTY_FROZENSET
    variables: re.Pattern[str] | None = None
    cmdlets: bool = False


_LANGUAGE_ALIASES: dict[str, str] = {
    "py": "python",
    "py3": "python",
    "python3": "python",
    "pyw": "python",
    "sh": "bash",
    "shell": "bash",
    "zsh": "bash",
    "bash": "bash",
    "console": "bash",
    "terminal": "bash",
    "ksh": "bash",
    "ps1": "powershell",
    "psm1": "powershell",
    "pwsh": "powershell",
    "js": "javascript",
    "jsx": "javascript",
    "mjs": "javascript",
    "cjs": "javascript",
    "node": "javascript",
    "ts": "typescript",
    "tsx": "typescript",
    "c++": "cpp",
    "cxx": "cpp",
    "cc": "cpp",
    "h": "c",
    "hpp": "cpp",
    "hh": "cpp",
    "hxx": "cpp",
    "cs": "csharp",
    "dotnet": "csharp",
    "golang": "go",
    "rs": "rust",
    "yml": "yaml",
    "jsonc": "json",
    "json5": "json",
    "postgres": "sql",
    "postgresql": "sql",
    "psql": "sql",
    "mysql": "sql",
    "sqlite": "sql",
    "plsql": "sql",
    "http": "http",
    "https": "http",
    "htm": "html",
    "svg": "html",
    "xhtml": "html",
    "xml": "html",
    "md": "markdown",
    "docker": "dockerfile",
    "cfg": "ini",
    "conf": "ini",
    "properties": "ini",
    "txt": "text",
    "plain": "text",
    "none": "text",
    "": "text",
}

_PYTHON_PREFIXES = frozenset({"r", "b", "u", "f", "rb", "br", "fr", "rf"})
_PYTHON_RAW_PREFIXES = frozenset({"r", "rb", "br", "fr", "rf"})
_SHELL_VARIABLES = re.compile(r"\$\{[^}\n]*\}|\$[A-Za-z_][A-Za-z0-9_]*|\$[0-9@*#?$!-]")
_ASM_VARIABLES = re.compile(r"%[A-Za-z_][A-Za-z0-9_]*|%[0-9]+")
_NUMBER_RE = re.compile(
    r"(?=\d|\.\d)(?:0[xX][0-9a-fA-F_]+|0[bB][01_]+|0[oO][0-7_]+"
    r"|\d[\d_]*(?:\.[\d_]*)?(?:[eE][+-]?\d+)?|\.\d+(?:[eE][+-]?\d+)?)[fFlLuU]*"
)
_IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*")
_CMDLET_RE = re.compile(r"^[A-Z][a-z]+-[A-Z][A-Za-z]+$")


def _spec(
    keywords: str = "",
    builtins: str = "",
    *,
    line_comments: tuple[str, ...] = (),
    block_comments: tuple[tuple[str, str, bool], ...] = (),
    quotes: tuple[str, ...] = ('"', "'", "`"),
    triples: tuple[str, ...] = (),
    prefixes: frozenset[str] = _EMPTY_FROZENSET,
    raw_prefixes: frozenset[str] = _EMPTY_FROZENSET,
    variables: re.Pattern[str] | None = None,
    cmdlets: bool = False,
) -> LanguageSpec:
    return LanguageSpec(
        frozenset(keywords.split()),
        frozenset(builtins.split()),
        line_comments,
        block_comments,
        quotes,
        triples,
        prefixes,
        raw_prefixes,
        variables,
        cmdlets,
    )


_C_STYLE_COMMENTS: tuple[tuple[str, str, bool], ...] = (("/*", "*/", False),)
_NESTED_COMMENTS: tuple[tuple[str, str, bool], ...] = (("/*", "*/", True),)

_SPECS: dict[str, LanguageSpec] = {
    "python": _spec(
        "and as assert async await break case class continue def del elif else except finally for "
        "from global if import in is lambda match nonlocal not or pass raise return try while with "
        "yield",
        "true false none self cls print len range open int str bytes float bool list dict set tuple "
        "enumerate zip sum min max sorted reversed super isinstance issubclass getattr setattr "
        "hasattr type repr input format map filter any all",
        line_comments=("#",),
        quotes=('"', "'"),
        triples=('"""', "'''"),
        prefixes=_PYTHON_PREFIXES,
        raw_prefixes=_PYTHON_RAW_PREFIXES,
    ),
    "bash": _spec(
        "if then else elif fi for while until do done case esac in function select time coproc "
        "export local readonly declare unset shift source eval exec exit return break continue",
        "echo cd pwd ls cat grep sed awk cut sort uniq head tail chmod chown curl wget nc ncat "
        "python python3 pip git docker nmap ffuf gobuster nikto sqlmap hydra sudo su",
        line_comments=("#",),
        variables=_SHELL_VARIABLES,
    ),
    "powershell": _spec(
        "if else elseif foreach for while do until switch function param begin process end try "
        "catch finally throw return trap break continue in",
        "true false null write-host get-childitem get-content set-content select-object where-object "
        "foreach-object invoke-webrequest invoke-expression start-process stop-process",
        line_comments=("#",),
        quotes=('"', "'"),
        variables=_SHELL_VARIABLES,
        cmdlets=True,
    ),
    "javascript": _spec(
        "const let var function return if else for while do switch case break continue class extends "
        "new this typeof instanceof in of async await try catch finally throw import export from "
        "default delete void yield static get set",
        "true false null undefined console document window require module process fetch promise "
        "array object string number boolean json math",
        line_comments=("//",),
        block_comments=_C_STYLE_COMMENTS,
    ),
    "typescript": _spec(
        "const let var function return if else for while do switch case break continue class extends "
        "new this typeof instanceof in of async await try catch finally throw import export from "
        "default delete void yield static get set interface type enum implements public private "
        "protected readonly namespace declare as satisfies abstract keyof infer is",
        "true false null undefined console document window require module process fetch promise "
        "array object string number boolean json math",
        line_comments=("//",),
        block_comments=_C_STYLE_COMMENTS,
    ),
    "sql": _spec(
        "select from where join inner left right full outer on group by order having limit offset "
        "insert into values update set delete create table drop alter index view and or not null is "
        "as distinct union all case when then else end exists in like between primary key foreign "
        "references unique constraint default database schema begin commit rollback",
        "count sum avg min max coalesce cast lower upper substr length now date",
        line_comments=("--",),
        block_comments=_NESTED_COMMENTS,
    ),
    "c": _spec(
        "auto break case char const continue default do double else enum extern float for goto if "
        "inline int long register restrict return short signed sizeof static struct switch typedef "
        "union unsigned void volatile while",
        "printf fprintf sprintf snprintf scanf malloc calloc realloc free memcpy memset strlen strcpy "
        "strncpy strcmp fopen fclose fgets fread fwrite",
        line_comments=("//",),
        block_comments=_C_STYLE_COMMENTS,
        quotes=('"', "'"),
    ),
    "cpp": _spec(
        "auto break case char const constexpr continue default delete do double else enum extern "
        "float for goto if inline int long namespace new nullptr operator override private protected "
        "public register return short signed sizeof static struct switch template this throw try "
        "typedef typename union unsigned using virtual void volatile while class",
        "printf cout cin cerr endl malloc free memcpy memset strlen string vector map set unique_ptr "
        "shared_ptr make_unique make_shared",
        line_comments=("//",),
        block_comments=_C_STYLE_COMMENTS,
        quotes=('"', "'"),
    ),
    "go": _spec(
        "break case chan const continue default defer else fallthrough for func go goto if import "
        "interface map package range return select struct switch type var",
        "fmt len make new append cap copy delete panic recover print println",
        line_comments=("//",),
        block_comments=_C_STYLE_COMMENTS,
    ),
    "rust": _spec(
        "as async await break const continue crate dyn else enum extern false fn for if impl in let "
        "loop match mod move mut pub ref return self static struct super trait true type unsafe use "
        "where while",
        "println print format vec some none ok err string vec option result",
        line_comments=("//",),
        block_comments=_NESTED_COMMENTS,
    ),
    "php": _spec(
        "abstract and array as break callable case catch class clone const continue declare default "
        "do echo else elseif empty enddeclare endfor endforeach endif endswitch endwhile eval exit "
        "extends final finally fn for foreach function global goto if implements include include_once "
        "instanceof insteadof interface isset list match namespace new or print private protected "
        "public readonly require require_once return static switch throw trait try unset use var "
        "while xor yield",
        "true false null strlen count array_map array_filter strpos preg_match isset unset echo",
        line_comments=("//", "#"),
        block_comments=_C_STYLE_COMMENTS,
        variables=_SHELL_VARIABLES,
    ),
    "ruby": _spec(
        "alias and begin break case class def defined do else elsif end ensure false for if in module "
        "next nil not or redo rescue retry return self super then true undef unless until when while "
        "yield",
        "puts print require attr_accessor true false nil",
        line_comments=("#",),
    ),
    "java": _spec(
        "abstract assert boolean break byte case catch char class const continue default do double "
        "else enum extends final finally float for goto if implements import instanceof int interface "
        "long native new package private protected public return short static strictfp super switch "
        "synchronized this throw throws transient try void volatile while var record sealed permits",
        "true false null system string integer list map optional exception",
        line_comments=("//",),
        block_comments=_C_STYLE_COMMENTS,
        quotes=('"', "'"),
    ),
    "csharp": _spec(
        "abstract as base bool break byte case catch char checked class const continue decimal default "
        "delegate do double else enum event explicit extern false finally fixed float for foreach "
        "goto if implicit in int interface internal is lock long namespace new null object operator "
        "out override params private protected public readonly ref return sbyte sealed short sizeof "
        "stackalloc static string struct switch this throw true try typeof uint ulong unchecked unsafe "
        "ushort using virtual void volatile while",
        "console string int object list dictionary task math convert",
        line_comments=("//",),
        block_comments=_C_STYLE_COMMENTS,
        quotes=('"', "'"),
    ),
    "swift": _spec(
        "as Any break case catch class continue default defer deinit do else enum extension fallthrough "
        "false for func guard if import in init inout internal let nil operator private protocol public "
        "repeat return self static struct subscript super switch throw throws true try typealias var "
        "where while",
        "print int string double bool array dictionary optional",
        line_comments=("//",),
        block_comments=_NESTED_COMMENTS,
    ),
    "kotlin": _spec(
        "as break class continue do else false for fun if in interface is null object package return "
        "super this throw true try typealias typeof val var when while by catch constructor data "
        "finally get set where",
        "println print list mutablelist map mutablemap string int boolean",
        line_comments=("//",),
        block_comments=_NESTED_COMMENTS,
    ),
    "lua": _spec(
        "and break do else elseif end false for function goto if in local nil not or repeat return then "
        "true until while",
        "print pairs ipairs require tonumber tostring type next",
        line_comments=("--",),
        block_comments=(("--[[", "]]", False),),
    ),
    "perl": _spec(
        "and cmp continue do else elsif eq for foreach ge given gt if last le local my ne next no or "
        "package print return sub unless until use when while xor",
        "true false undef sprintf length push pop shift unlink",
        line_comments=("#",),
        variables=_SHELL_VARIABLES,
    ),
    "json": _spec("true false null", line_comments=(), quotes=('"',)),
    "yaml": _spec(
        "true false null yes no on off",
        line_comments=("#",),
    ),
    "http": _spec(
        "get post put patch delete head options connect trace host user-agent accept",
        line_comments=("#",),
        quotes=(),
    ),
    "html": _spec(
        "",
        "div span a p h1 h2 h3 h4 h5 h6 body head title meta link script style section article nav",
        block_comments=(("<!--", "-->", False),),
        quotes=('"', "'"),
    ),
    "css": _spec(
        "important media print screen supports",
        block_comments=_C_STYLE_COMMENTS,
        quotes=('"', "'"),
    ),
    "ini": _spec(
        "true false yes no on off",
        line_comments=("#", ";"),
    ),
    "toml": _spec(
        "true false",
        line_comments=("#",),
        quotes=('"', "'"),
    ),
    "dockerfile": _spec(
        "from as run cmd label maintainer expose env add copy entrypoint volume user workdir arg "
        "onbuild storagesignal healthcheck shell",
        line_comments=("#",),
    ),
    "markdown": _spec("", quotes=()),
    "text": _spec("", quotes=()),
}


def normalize_language(language: str) -> str:
    cleaned = language.strip().lower().lstrip(".")
    return _LANGUAGE_ALIASES.get(cleaned, cleaned)


def supported_languages() -> tuple[str, ...]:
    """Return the canonical languages the highlighter can color."""
    return tuple(sorted(_SPECS))


def tokenize_code(code: str, language: str = "") -> list[CodeToken]:
    """Split code into colored tokens while preserving every character."""
    if not code:
        return []
    lang = normalize_language(language)
    spec = _SPECS.get(lang)
    if spec is None:
        return [CodeToken("text", code)]
    return _scan(code, spec)


def _scan(code: str, spec: LanguageSpec) -> list[CodeToken]:
    tokens: list[CodeToken] = []
    position = 0
    length = len(code)
    while position < length:
        matched = _scan_comment(code, position, spec, tokens)
        if matched is not None:
            position = matched
            continue

        string = _scan_string(code, position, spec)
        if string is not None:
            string_end, string_text = string
            tokens.append(CodeToken("string", string_text))
            position = string_end
            continue

        if spec.variables is not None:
            variable = spec.variables.match(code, position)
            if variable is not None:
                tokens.append(CodeToken("variable", variable.group(0)))
                position = variable.end()
                continue

        number = _NUMBER_RE.match(code, position)
        if number is not None:
            tokens.append(CodeToken("number", number.group(0)))
            position = number.end()
            continue

        identifier = _IDENTIFIER_RE.match(code, position)
        if identifier is not None:
            value = identifier.group(0)
            tokens.append(CodeToken(_classify_word(value, spec), value))
            position = identifier.end()
            continue

        tokens.append(CodeToken("text", code[position]))
        position += 1
    return _coalesce(tokens)


def _scan_comment(
    code: str, position: int, spec: LanguageSpec, tokens: list[CodeToken]
) -> int | None:
    for opening, closing, nested in spec.block_comments:
        if code.startswith(opening, position):
            end = _scan_block(code, position + len(opening), opening, closing, nested)
            tokens.append(CodeToken("comment", code[position:end]))
            return end
    for marker in spec.line_comments:
        if code.startswith(marker, position):
            end = code.find("\n", position)
            tokens.append(CodeToken("comment", code[position : end if end >= 0 else len(code)]))
            return end if end >= 0 else len(code)
    return None


def _scan_block(code: str, position: int, opening: str, closing: str, nested: bool) -> int:
    depth = 1
    length = len(code)
    while position < length:
        if nested and code.startswith(opening, position):
            depth += 1
            position += len(opening)
            continue
        if code.startswith(closing, position):
            depth -= 1
            position += len(closing)
            if depth == 0:
                return position
            continue
        position += 1
    return length


def _scan_string(code: str, position: int, spec: LanguageSpec) -> tuple[int, str] | None:
    for triple in spec.triples:
        if code.startswith(triple, position):
            end = _scan_quoted(code, position + len(triple), triple, False)
            return end, code[position:end]
    if not spec.quotes:
        return None
    for prefix in sorted(spec.prefixes, key=len, reverse=True):
        if code[position : position + len(prefix)].casefold() != prefix:
            continue
        quote_position = position + len(prefix)
        if quote_position >= len(code) or code[quote_position] not in spec.quotes:
            continue
        closing = code[quote_position]
        raw = prefix in spec.raw_prefixes
        end = _scan_quoted(code, quote_position + 1, closing, raw)
        return end, code[position:end]
    if code[position] in spec.quotes:
        closing = code[position]
        end = _scan_quoted(code, position + 1, closing, False)
        return end, code[position:end]
    return None


def _scan_quoted(code: str, position: int, closing: str, raw: bool) -> int:
    length = len(code)
    while position < length:
        if code[position] == "\\" and not raw and position + 1 < length:
            position += 2
            continue
        if code.startswith(closing, position):
            return position + len(closing)
        if len(closing) == 1 and code[position] == "\n":
            return position
        position += 1
    return length


def _classify_word(value: str, spec: LanguageSpec) -> str:
    lowered = value.lower()
    if lowered in spec.keywords:
        return "keyword"
    if lowered in spec.builtins:
        return "builtin"
    if spec.cmdlets and _CMDLET_RE.match(value):
        return "builtin"
    return "text"


def _coalesce(tokens: list[CodeToken]) -> list[CodeToken]:
    merged: list[CodeToken] = []
    for token in tokens:
        if merged and merged[-1].kind == token.kind:
            merged[-1] = CodeToken(token.kind, merged[-1].text + token.text)
        else:
            merged.append(token)
    return merged
