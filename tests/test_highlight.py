from __future__ import annotations

from redscribe.content.highlight import CodeToken, normalize_language, tokenize_code


def _joined(tokens: list[CodeToken]) -> str:
    return "".join(token.text for token in tokens)


def test_normalize_language_aliases() -> None:
    assert normalize_language("PY") == "python"
    assert normalize_language(" .py ") == "python"
    assert normalize_language("sh") == "bash"
    assert normalize_language("ps1") == "powershell"
    assert normalize_language("tsx") == "typescript"
    assert normalize_language("") == "text"


def test_tokenize_python() -> None:
    code = "def run(x):\n    # comment\n    return 'value' + 42\n"
    tokens = tokenize_code(code, "py")
    assert _joined(tokens) == code
    kinds = {token.kind for token in tokens}
    assert "keyword" in kinds
    assert "comment" in kinds
    assert "string" in kinds
    assert "number" in kinds
    assert "builtin" not in kinds
    assert any(token.kind == "keyword" and token.text == "def" for token in tokens)
    assert any(token.kind == "comment" and "comment" in token.text for token in tokens)


def test_tokenize_bash_variables_and_builtins() -> None:
    code = "target=$1; echo $target; nc -lvnp 4444\n"
    tokens = tokenize_code(code, "bash")
    assert _joined(tokens) == code
    assert any(token.kind == "variable" and token.text == "$1" for token in tokens)
    assert any(token.kind == "variable" and token.text == "$target" for token in tokens)
    assert any(token.kind == "builtin" and token.text == "echo" for token in tokens)
    assert any(token.kind == "number" and token.text == "4444" for token in tokens)


def test_tokenize_unknown_language_returns_plain_text() -> None:
    assert tokenize_code("hello", "made-up") == [CodeToken("text", "hello")]
    assert tokenize_code("", "python") == []


def test_tokenize_powershell_cmdlets() -> None:
    tokens = tokenize_code("Get-ChildItem -Path C:\\ | Select-Object Name", "pwsh")
    assert _joined(tokens) == "Get-ChildItem -Path C:\\ | Select-Object Name"
    assert any(token.kind == "builtin" and token.text == "Get-ChildItem" for token in tokens)
    assert any(token.kind == "builtin" and token.text == "Select-Object" for token in tokens)


def test_tokenize_block_comment() -> None:
    code = "int main(void) {\n    /* block comment */\n    return 0;\n}\n"
    tokens = tokenize_code(code, "c")
    assert _joined(tokens) == code
    assert any(token.kind == "comment" and "block" in token.text for token in tokens)


def test_tokenize_multiline_block_comment() -> None:
    code = "/* first line\nsecond line */\nint value = 1;\n"
    tokens = tokenize_code(code, "c")
    assert _joined(tokens) == code
    assert any(
        token.kind == "comment" and token.text == "/* first line\nsecond line */"
        for token in tokens
    )


def test_tokenize_python_triple_quoted_strings() -> None:
    code = 'def run():\n    """First line.\n    Second line."""\n    return 1\n'
    tokens = tokenize_code(code, "py")
    assert _joined(tokens) == code
    assert any(
        token.kind == "string" and token.text.startswith('"""First line.\n') for token in tokens
    )
    assert any(token.kind == "keyword" and token.text == "def" for token in tokens)


def test_tokenize_preserves_unicode_and_line_endings() -> None:
    code = "echo 'héllo'\r\n# naïve comment\r\n"
    tokens = tokenize_code(code, "bash")
    assert _joined(tokens) == code
    assert any("héllo" in token.text for token in tokens)
    assert any(token.kind == "comment" and "naïve" in token.text for token in tokens)
