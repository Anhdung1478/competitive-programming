# Statement markup on Polygon

The upload convention for [uploading-to-polygon](../SKILL.md)'s Phase 3: how
a vnolymp `.tex` becomes the fields `polygon_save_statement` takes, and what
TeX survives the trip.

**Why a convention at all.** Polygon keeps two renderers. The PDF is real
LaTeX and accepts almost anything. The HTML that Codeforces shows
contestants goes through Polygon's own converter, which supports a short,
fixed list of text-mode commands. A statement can build a clean PDF and still
render as broken or blank HTML. Nothing in the API reports that — the failure
shows up only in the Polygon web UI, or in front of contestants.

Sources: Polygon's *Statements TeX manual*
(`https://polygon.codeforces.com/docs/statements-tex-manual`, needs a Polygon
login), and the constructs that actually broke while five Trinity Force
problems were uploaded on 2026-09-14. The manual is the authority on what is
supported; the field list below is the authority on what went wrong anyway.

## Delimiters

| What | Write | Never |
|---|---|---|
| inline math | `$a_i \le 10^9$` | `$$$…$$$`, `\(…\)` |
| display math, centred | `$$\sum_{i=1}^{n} a_i$$` | `\[…\]`, `equation`, `align` |

`$$$x$$$` is the delimiter of problems created **before 1 Jun 2021**, which
render formulas without MathJax. Every problem this skill creates is newer
than that, so `$$$` is always wrong here. It is legacy markup to recognise
when re-syncing an old problem, not a style to copy.

A new paragraph is a blank line. `\\` breaks a line inside one.

## Fields

`polygon_save_statement` takes one string per section. There is no
constraints field, and samples are not part of any field.

| vnolymp source | Polygon field | Convention |
|---|---|---|
| `problem.json`'s `title` in the `.tex`'s language | `name` | plain text, no TeX |
| story and task, up to and including the closing requirement line (`\textbf{Yêu cầu:}`, `\textbf{Task:}`) | `legend` | |
| `\InputFile` | `input` | the `itemize` describing the lines |
| `\Constraints` | `input`, appended | a blank line, a bold label in the statement's language (`\textbf{Giới hạn}`, `\textbf{Constraints}`), then the same `itemize` of bounds. Polygon has no field for it, and the input section is where a reader looks for bounds |
| `\OutputFile` | `output` | |
| `subtasks` environment, `format == "oi"` only | `scoring` | a `tabular`, see below; omit the field entirely for `icpc` |
| `\Explanation` | `notes` | narrates the samples by number, in the order Polygon shows them |
| `\Note` | `notes`, after the explanation | |
| `\Examples` / `\exmpfile` | — | never written into any field. Samples are tests marked `use_in_statements` (Phase 6), so Polygon renders them from the tests it actually has |
| `\includegraphics` figures | `polygon_save_statement_resource` | upload the image first, then reference it by its bare name |

Everything else inside `\begin{problem}` has no Polygon counterpart and is
dropped: the key list, `\exmpfile` lines, package-specific macros, `%`
comments, and any block the `.tex` switches off (a commented-out or
`\iffalse` `subtasks` block is not a scoring table). Two rewrites apply
throughout: `\emph{…}` becomes `\textit{…}`, and `$$$` becomes `$`.

## Text mode: the whole supported list

Anything not in this table is unsupported in the HTML, even when the PDF
builds.

| Purpose | Commands |
|---|---|
| bold, italic | `\textbf{}`, `\bf`; `\textit{}`, `\it` |
| monospace | `\texttt{}`, `\tt`, `\t`; `\verb|…|` when the text holds special characters |
| underline, strike-out, small caps | `\underline{}`; `\sout{}`; `\textsc{}` |
| **`\emph{}`** | renders as **underline**, not italics — use `\textit{}` for italics |
| size | `\tiny` `\scriptsize` `\small` `\normalsize` `\large` `\Large` `\LARGE` `\huge` `\Huge` |
| lists | `itemize`, `enumerate`, `\item` |
| code | `lstlisting` |
| centring | `center` |
| tables | `tabular`, `\hline`, `\cline`, `\multicolumn`, `\multirow` |
| links | `\url{}`, `\href{}{}` |
| images | `\includegraphics{}`, with `[scale=…]` or `[width=…cm]`; `\def\htmlPixelsInCm{…}` |
| epigraph | `\epigraph{quote}{--- author}` |
| characters | `~` (non-breaking space), `--`, `---`, `` ``…'' ``, `<<…>>`, `\% \$ \& \_ \# \{ \}` |

Vietnamese diacritics go in as UTF-8 text; no TeX accents are needed.

## Math mode

Formulas are rendered by MathJax, and the manual says math mode is not
otherwise restricted. The constructs below were nonetheless observed to break
the Codeforces HTML, so the lint rejects them:

| Broke | Why it hurts | Write instead |
|---|---|---|
| `\emph{nguyên vẹn sau $k$ lần xoá}` | a `$` inside a text command's braces | close the command before the formula: `\textit{nguyên vẹn sau} $k$ \textit{lần xoá}`, or rephrase so the formula sits outside |
| `$P(5) = \texttt{aabaa}$` | a text command inside math | `$P(5) =$ \texttt{aabaa}` |
| `$\text{lên } (0,+1)$` | `\text` inside math | `lên $(0, +1)$` |
| `$\mathrm{dist}(u,v)$` | made the whole prototype statement unrenderable | a one-letter name defined in words — "let $d(u, v)$ be the least number of streets…" — which reads correctly in MathJax. A bare `$dist(u, v)$` lints clean but renders as the product $d \cdot i \cdot s \cdot t$ |
| `$\{2$--$3, 3$--$1\}$` | one set literal split across several spans leaves `\{` and `\}` in different spans | keep the whole literal in one span, with no text inside it: `$\{(2, 3), (3, 1)\}$` |

The same rule covers `\textrm`, `\textbf`, `\textit`, `\mbox` and
`\operatorname` inside a formula. Each math span must be balanced on its own,
counting both `{…}` and `\{…\}`.

## Scoring table

For `format == "oi"`, the manual's own pattern, with the columns in the
statement's language:

```latex
\begin{center}
\begin{tabular}{|c|c|c|c|}
\hline
\textbf{Subtask} & \textbf{Ràng buộc bổ sung} & \textbf{Điểm} & \textbf{Subtask yêu cầu} \\
\hline
$1$ & $n \le 10$ & $20$ & --- \\
\hline
$2$ & $n \le 5000$ & $30$ & $1$ \\
\hline
$3$ & không có & $50$ & $1, 2$ \\
\hline
\end{tabular}
\end{center}
```

The rows are read from `problem.json` (`subtasks[].points`, `depends_on`),
never retyped from the `.tex`. Those are the values Phase 7 uploads as
groups and points.

## Figures

1. `polygon_save_statement_resource(problem_id, name="figure-1.png", path=…)`.
2. In the field:

```latex
\begin{center}
\includegraphics{figure-1.png} \\
\small{Hình 1.}
\end{center}
```

`[width=4.5cm]` is converted to pixels as width × `\htmlPixelsInCm`, which
defaults to 37.8. Centre and caption every image; the manual recommends both.

## Check before saving

Assemble the fields into one JSON object in a scratch directory — **not**
inside the package, since `polygon.json` is the only file this skill writes
there — and lint it:

```bash
python3 -m tools.cf_statement_lint "$SCRATCH/polygon-statement.json"
```

Exit 0 means no errors. Warnings may stand, but read them. Exit 1 lists each
offending field with its line, column and kind. Fix the JSON, never the
package's `.tex` — the PDF is already reviewed — and lint again. The linter
cannot see the Polygon UI's render, so after the commit, tell the user to
open the statement preview once.
