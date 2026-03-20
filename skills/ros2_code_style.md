# ROS 2 Code Style & Language Versions — Skill File

> Source: https://docs.ros.org/en/jazzy/The-ROS2-Project/Contributing/Code-Style-Language-Versions.html
> Distro: Jazzy Jalisco

---

## Philosophy

- Follow externally defined style guides per language where possible.
- Use integrated editor tools (linters, formatters) to check style.
- Packages should check style as part of unit tests via `ament_lint_auto`.

---

## C

### Standard: C99

### Style: PEP7 (modified)

- Target C99 (not C89 as PEP7 recommends) — allows `//` and `/* */` comments.
- C++ style `//` comments allowed.
- (Optional) Place literals on left-hand side of comparisons: `0 == ret` instead of `ret == 0`.
- Do NOT use `Py_` prefix (use CamelCase package name prefix instead).
- Python documentation string rules don't apply.
- Linter: `pep7` Python module.

---

## C++

### Standard: C++17 (Jazzy)

### Style: Google C++ Style Guide (modified)

#### Line Length
- **Maximum 100 characters per line.**

#### File Extensions
- Headers: `.hpp`
- Implementation: `.cpp`

#### Naming

| Element | Convention | Example |
|---|---|---|
| Functions/Methods | `snake_case` (preferred in ROS 2 core) or `CamelCase` | `get_value()` |
| Classes | `CamelCase` | `LaserScanner` |
| Variables | `snake_case` | `scan_data` |
| Global variables | `g_` prefix + `snake_case` | `g_node_count` |
| Constants | Mixed — `snake_case`, `PascalCase`, or `UPPER_CASE` | Follow surrounding code |

**Note**: ROS 2 deviates from Google style (`kPascalCase` for constants). Prefer consistency with existing surrounding code.

#### Braces

- **Open braces** for `function`, `class`, `enum`, `struct` definitions.
- **Cuddled braces** for `if`, `else`, `while`, `for`, etc.
- **Exception**: If `if`/`while` condition wraps lines → use open brace.

```cpp
// CORRECT
int main(int argc, char **argv)
{
  if (condition) {
    return 0;
  } else {
    return 1;
  }
}

// Long condition → open brace
if (
  this && that || both && this && that || both)
{
  ...
}

// NOT correct
int main(int argc, char **argv) {
  return 0;
}
```

#### Function Calls
- If can't fit on one line → wrap at open parenthesis, 2-space indent on next lines.

```cpp
call_func(
  foo, bar, foo, bar, foo, bar,
  foo, bar, foo, bar);
```

#### Constructor Initializer Lists

```cpp
MyClass::MyClass(int var)
: some_var_(var),
  some_other_var_(var + 1)
{
  DoSomething();
}
```

#### Key Rules

| Rule | Detail |
|---|---|
| **Always use braces** | Even for single-line `if`/`else`/`while`/`for` bodies |
| **Nested templates** | `set<list<string>>` — no whitespace |
| **Pointer syntax** | `char * c;` not `char* c;` or `char *c;` |
| **Class privacy keywords** | `public:`/`private:`/`protected:` at column 0 (preferred) or 2-space indent |
| **Exceptions** | Allowed (new codebase); avoid in C-wrappable APIs; never in destructors |
| **Boost** | Avoid unless absolutely required |
| **Lambda/std::function/std::bind** | No restrictions |
| **Access control** | Prefer private members; use accessors; only make public with good reason |

#### Comments and Documentation

```cpp
/// Doxygen single-line doc comment
/** Doxygen multi-line doc comment */
// Regular code comment
```

- Use `///` and `/** */` for class/function documentation (Doxygen/Sphinx).
- Use `//` for implementation notes.

#### Linters

| Tool | Purpose |
|---|---|
| `ament_cpplint` | Google cpplint checks |
| `ament_uncrustify` | Code formatting (supports `--reformat`) |
| `ament_clang_format` | Clang-format checks (supports `--reformat`) |
| `ament_cppcheck` | Static analysis |

Additional compiler flags: `-Wall -Wextra -Wpedantic`

---

## Python

### Version: Python 3

### Style: PEP 8 (with ROS 2 modifications)

| Rule | ROS 2 Choice |
|---|---|
| Max line length | **100 characters** |
| String quotes | **Single quotes** (unless escaping needed) |
| Continuation lines | **Hanging indents** preferred |
| Imports | **One import per line** |

```python
# Preferred
from typing import Dict
from typing import List

# NOT preferred
from typing import Dict, List
from typing import (
  Dict,
  List,
)
```

### Linter
- `ament_pycodestyle` — config: https://github.com/ament/ament_lint/blob/jazzy/ament_pycodestyle/ament_pycodestyle/configuration/ament_pycodestyle.ini

---

## CMake

### Minimum Version
Per REP 2000: currently 3.14.4 (ROS Humble on macOS).

### Style

- Lowercase command names: `find_package`, not `FIND_PACKAGE`.
- `snake_case` identifiers.
- Empty `else()` and `end...()` commands.
- No whitespace before `(`.
- **2-space indentation**, no tabs.
- No aligned indentation for multi-line macro params — just 2 spaces.
- Prefer functions with `set(PARENT_SCOPE)` over macros.
- Prefix local variables in macros with `_` or a reasonable prefix.

---

## Markdown / reStructuredText / Docblocks

### All Doc Types
- Each sentence starts on a **new line** (better diffs for long paragraphs).
- Sentences can optionally be wrapped to keep lines short.
- No trailing whitespace on lines.

### Markdown or RST
- One empty line before and after each section title.
- One empty line before and after each code block.
- Code blocks should specify syntax (e.g. `bash`, `cpp`).

### RST Heading Hierarchy
1. `#` with overline (document title only)
2. `*` with overline
3. `=`
4. `-`
5. `^`
6. `"`

### Markdown Heading Style
- ATX-style: `# Heading 1`, `## Heading 2`, etc.
- Space between `#` and title text.
