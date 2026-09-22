---
name: writing-editorials
description: >
  Use ONLY when this conversation explicitly asks for an editorial,
  editorial.html, a solution writeup, a tutorial page, or a whole-contest
  editorial — one standalone HTML file with a lore-stripped restatement,
  the derivation that reaches the intended solution, and the time
  complexity. Finishing competitive-programming:creating-problems is not
  such a request. Not the vnolymp .tex statement.
---

# Writing editorials

The deliverable is one HTML file that needs nothing but a browser, and it
scrolls rather than paginating. It explains a solved problem to the
contestants who could not solve it, which is a different job from every
other skill here — those build the package, this one explains it
afterwards. The skill is **opt-in and detached**: not a phase of the
setting pipeline, no gate to satisfy, nothing downstream waiting on it.

## Am I the right skill?

| If it's really about | Use |
|---|---|
| The vnolymp `.tex` statement contestants read during the round | `competitive-programming:writing-statements` |
| Building the package — tests, model, validation, audit | `competitive-programming:creating-problems` |
| Auditing a finished package before it ships | `competitive-programming:reviewing-problems` |
| The C++ itself, or a problem nobody has solved yet | `competitive-programming:solving-problems` |

**Run only if the request is explicit.** "Write the editorial",
"editorial.html", "a solution writeup for this", "tutorial page" — those
are requests. Silence after `creating-problems` signs a package off is
**not** one, and neither is a package that happens to have an `editorial/`
directory already. If a single request says both — "prepare this problem
and write the editorial" — run the pipeline first and come here after
`reviewing-problems` has audited the package, because until then the
editorial would be restating a statement still being edited.

## Read first

- The statement: the `.tex` under the problem directory, or whatever the
  user pasted into the conversation.
- `problem.json` if the problem has one — `constraints`, `subtasks`,
  `tags`, and the two limits the header prints,
  `limits.time_ms_published` and `limits.memory_mb`. If either limit is
  missing, ask rather than invent one; a wrong TL on the page is exactly
  the kind of error a reader trusts.
- `sol-main.cpp`, the intended solution. A second accepted solution, if
  one exists, is where the optional "Other solutions" section comes from.

**Cross-check the restatement against the official statement before you
write a word of the tutorial.** Everything after it is built on top, so a
restatement error propagates into the derivation and is invisible
afterwards. The four that bite: subtask points and per-rung bounds; the
output format (a matrix of characters is not one character per line); the
problem-defining guarantees (acyclic or not, directed or not, self-loops,
parallel edges, connectivity); and the exact object being optimized. If
the restatement is wrong, fix it first, then re-derive every paragraph
that leaned on the wrong claim.

Lead the chat reply with the **expected difficulty** — a Codeforces-style
rating and one line saying why — and put that same **plain number** in the
page's `Difficulty` field: `2100`, not `*2100`. The user sets the official
value later; if they give a different one, change only that field. Propose
CF-style tags (`data structures`, `greedy`, …) and use them unless they
override, but do not block the page on tags. English unless the user asked
for Vietnamese.

**If `$PROBLEM/difficulty.md` exists, that number is the one to use** — copy
it, say in the chat reply that it came from there, and do not re-estimate.
`calculating-difficulties` wrote it by placing the problem against real rated
anchors under a blind-calibrated rubric, and a second free-hand estimate
sitting beside it is a contradiction with no tiebreaker. If that file says
`not estimable`, leave the `Difficulty` field for the user to fill rather than
substituting a guess for the estimate the other skill declined to make.

## Output

```text
$PROBLEM/editorial/editorial.html
```

Create `editorial/` if it does not exist. If an `editorial.md` is already
there, do not delete it — treat it as source material and reshape it into
the structure below rather than pouring a markdown essay into HTML.

The file must run **alone**: opened from the filesystem, no npm, no local
server, no sibling files. CDN fonts and KaTeX are fine, because the theme
already loads them.

## The theme, and the frame it gives you

The default and only shipped theme is
`references/themes/space-dark.html`. Copy its `<head>`, `:root` tokens and
chrome **verbatim**, fill the slots, and change nothing else — no in-page
theme toggle, no second theme mixed in, no wider or narrower page. Themes
are personal taste and this skill carries no catalogue of them: if the
user wants a different look, ask them for a theme file or adapt this one
on request, and either way the result is a new file under
`references/themes/`, never an edit to the default's tokens.

That file is the contract. It exposes these slots, and filling them is
most of the work:

| Slot in the theme | What goes in |
|---|---|
| `<!-- PROBLEM_NAME -->` (four places: `<title>`, `.bar-name`, `h1`, footer) | The problem name. The `h1` is `A. Name` on a contest page |
| `<!-- TIME_LIMIT ... -->` | `limits.time_ms_published`, written as a human limit (`2 s`) |
| `<!-- MEMORY_LIMIT ... -->` | `limits.memory_mb` (`256 MB`) |
| `<!-- EXPECTED_RATING ... -->` | The plain rating number |
| `<li class="tag">` in `ul.tags` | One per tag |
| `section#statement` | The restatement, Requirement, Constraints, Subtask list |
| `section#tutorial` | The derivation |
| `section#complexity` | The `.complexity` div |
| `section#other`, `section#fun` | Optional; delete the section when there is nothing to put in it, and emit `#fun` only if the user asked for a fun fact |
| `section.subtask` | One per rung, only when the problem has subtasks |
| `div.toc`, `section.problem` | Whole-contest pages only |

The bar kicker, the `<title>` suffix and the footer all read **Solution**.
Do not put a kicker above the `h1` — no "Problem", no "Bài C". The
heading is enough.

## The problem section

Restate the problem plainly, fiction stripped out: a merchant crossing
cities becomes a walk in a graph, two named rivals become the first and
second player. Every rule that can change an answer survives, nothing
else does, and a name stays only when stripping it costs more than the
fiction did. The order is fixed — Requirement is the last line of the
restatement, immediately above Constraints, not after the subtask list:

```html
<section id="statement">
  <h2>The problem</h2>
  <p>… lore-stripped restatement, with <mark>…</mark> …</p>
  <p><strong>Requirement:</strong> …what to compute…</p>
  <p><strong>Constraints:</strong></p>
  <ul>… global bounds …</ul>
</section>
```

Highlight the load-bearing facts with `<mark>`: who moves first, what is
chosen when, who knows what, an unusual modulus, a tie-break rule, an
unusual I/O convention. Highlight them even when the original statement
did not. Two to five marks is typical; marking everything marks nothing.

Visible subtask names are **Subtask 1**, **Subtask 2**, … — never
\(g_1\) or `g1` in prose, though the HTML `id` may stay `g1`. If the
problem has no subtasks, omit the list: **do not name the contest format**
(OI / IOI / ICPC) and do not write a sentence saying there are none.

## The tutorial is a derivation, not a summary

The goal is not brevity. It is that a strong contestant who failed this
problem can rebuild the algorithm from the page alone, with no step left
for them to invent. Write the way a contestant explains their own
solution to another contestant: a continuous chain,
each link motivated by the one before it — what makes the problem hard →
the observation → why it is true → what it lets us forget → the
representation that suggests → the state → the transition → why that is
correct → what it costs. A reader should never have to ask "why did we
look at that?" or "why is this state enough?"; if an answer is missing,
the explanation is not finished.

**Never compress non-obvious reasoning.** "From this we can use DP",
"therefore we maintain a segment tree", "the problem now becomes a
standard …" are fine only when the reasoning they skip is genuinely
trivial. Compare:

> Each query is clearly a range maximum, so we use a segment tree.

with

> A query asks for the best value over a contiguous block, and updates
> touch one position at a time. So we need a structure that answers an
> arbitrary block without rescanning it and absorbs a point change without
> rebuilding: a tree over the array's halves does both, at a logarithmic
> cost each.

The first hands the reader a conclusion; the second lays out the two
demands that force it, so the reader could have reached it alone.

The same rule holds for every piece the reader has to carry:

- **A state.** Say what it represents, why that is sufficient, what is
  being discarded, how it changes. Never use notation you did not define.
- **A transition.** Derive it: what the choices are, where each leads, why
  those are all of them, why the resulting value is the optimum.
- **A formula.** Define every variable and say where the formula came from
  before you display it.
- **Correctness.** Let it fall out of the derivation: the invariant, why
  it holds initially, why each operation preserves it, why the final state
  answers the question. When the derivation already carries the proof, do
  **not** append a paragraph restating it. "It is obvious that this is
  correct" is never a justification — if it is obvious, write the sentence
  that makes it so.
- **Complexity.** Say where it comes from, not just what it is: each
  element enters the structure once and each update costs \(O(\log N)\),
  so the total is \(O(N \log N)\). Give the memory bound when it matters.
- **Implementation the algorithm does not imply.** Why this structure, how
  indices are laid out, how lazy propagation is encoded, why `long long`
  is required. There is no code on the page, so this prose is what lets a
  reader write it.

Mention an edge case only when it clarifies correctness or implementation
— `N = 1`, duplicate values, a disconnected graph, overflow — and say why
it matters; a generic list at the end helps nobody.

Calibrate depth to who still needs the editorial. A classical
first-technique problem gets a few sentences introducing the structure
itself; a ~1400–1900 problem gets a one-line reminder only when the twist
is unusual; at 2000+ assume segment trees, DSU, binary lifting and
standard DP and explain only what is specific to this problem. Page length
is not a measure of difficulty.

## What earns a card

A card interrupts the prose, so it has to earn the interruption. Reserve
**Observation** for a claim the rest of the solution genuinely rests on —
remove it and the derivation breaks — and **Lemma** for a genuine lemma,
one whose proof is the substance. Everything else stays in the flow as
prose: "two equal weights can never be adjacent", a line of algebra, a
state that is sufficient for a reason you have just given.

There is **no Transformation box.** A transformation that opens the
solution — reading the operations backwards, rewriting a cost as a sum
over pairs so it stops depending on the input — is pivotal, and pivotal
claims are Observations. A routine change of view stays in prose.

The shapes worth a box are recognizable: the problem-closing step that
turns the last piece of reasoning into the recurrence; a rewrite that
strips the input's influence out of the objective; the transformation that
makes the solution visible at all. A typical tutorial has zero or one box,
occasionally two when the pivots are genuinely distinct. If you are
writing Observation 1, 2, 3 for routine steps, they belong back in the
prose; do not invent cards to look complete.

Between two halves of the derivation a **bridge** — a plain sentence, not
a card — carries the reader across: "we can now do this in \(O(N^2)\), but
that is still too slow, and the bottleneck is …".

Do not over-structure the rest of the page either. Avoid heading ladders
(Observation / Key Observation / Approach / Better Approach / Final
Approach / Conclusion). A good editorial is often just The problem →
Solution → Time complexity, plus Other solutions when there is one.

## Voice

The page is for the contestant, not for whoever set the problem. State the
mathematics and leave the setter's asides out: "do not apply observation
\(k\) in this branch", "the old constraint made this unreachable". Where a
case comes down to a closed form, the closed form is the whole explanation.

**Avoid the writing signals that mark generated prose.** These are
concrete, and each one is worth a pass over the draft:

- **Em dashes as the default connector.** Prefer commas, full stops,
  parentheses, or a new sentence; use `—` where it is the right
  punctuation, not as glue.
- **Binary contrast templates.** "This is not a problem about X. It is a
  problem about Y." Say the reasoning instead of framing it as a reversal.
- **Manufactured emphasis.** "This is the key insight." "Surprisingly, …"
  If something matters, show why.
- **Meta-commentary.** "Let us now look at …", "In this section we will
  …", "As mentioned above …" — cut unless they genuinely help.
- **One sentence rhythm repeated.** "We notice / from this / therefore"
  marching down the page reads as a template.
- **Synonym cycling.** If `vertex`, `edge`, `state` is the right word,
  repeat it. Precision beats lexical variety.
- **Bullets standing in for prose.** Bullets when the items are genuinely
  independent, prose when they form a chain.

Human is not the same as casual: no jokes, no filler, no anecdotes. The
target is clear, precise, naturally connected prose that happens to be
formal. Whatever the statement calls a variable, call it that, in that
case: an input written \(N\) is never \(n\) here. Symbols the editorial
invents may go either way, so long as the page does not switch halfway.

## Vietnamese pages

When the user asked for Vietnamese, read
`references/vi-glossary.md` **before writing** and set `<html lang="vi">`.
Translate for meaning, not word for word: write the Vietnamese a strong
olympiad contestant would actually say, use `ta` naturally, and vary the
connectors ("Từ đó", "Vì vậy", "Nói cách khác", "Bây giờ ta chỉ còn cần")
rather than transliterating English sentence shapes.

Two rules the glossary exists to hold: compound nouns keep Vietnamese
order (**đơn đồ thị**, never *đồ thị đơn*), and the page chrome stays in
English — Time limit, Memory limit, Difficulty, Tags, Solution, Other
solutions, Time complexity, Observation, Lemma, Fun fact, the word
Subtask, amortized / non-amortized, and every technique name. The heading
is Đề bài, and Yêu cầu sits above Giới hạn. If the user corrects a
translation, update the glossary in the same turn — not only the HTML.

## Problems with subtasks

Only when the problem actually has them. Put the observations every rung
uses in a global section first, then one `section.subtask` per rung with
its bounds, its points, the observations that exist only for it, and its
**own** time complexity. A rung that is an optimization of an earlier one
says so ("start from Subtask 2; the bottleneck is …") instead of repeating
it. After the last rung, a compact table: Subtask → insight → time. If
the user says the problem needs no per-rung writeup, keep one tutorial and
still list the subtasks in the problem section.

## Whole-contest editorial

When the user asks for one page covering every problem, write it to
`$CONTEST/editorial/editorial.html` in the same theme. The bar name is the
contest id, there is no introductory paragraph explaining the layout, and
there are **no iframes** — each problem's body is copied into a
`<section class="problem" id="a">` with its inner ids prefixed
(`a-statement`, `a-tutorial`, …). A `div.toc` at the top lists the
problems; tags inside it go in a `<ul class="tags">` so they wrap.

The per-problem files still exist, so the contest page is a second copy of
prose that lives somewhere else. **Any later fix lands in both files in
the same turn** — a restatement correction, a subtask point, a rewritten
tutorial. Match by section id when you replace, and verify each id you
targeted exists; drift between the two copies is invisible until a reader
finds it.

## `sol-editorial.cpp`, when code is asked for

Only when the user asks for code that matches the editorial. One
self-contained file at `$PROBLEM/sol-editorial.cpp`.

- **Mirror the editorial, not `sol-main.cpp`.** Where the two deliberately
  differ, follow the tutorial — the file exists so a reader can see the
  prose as code.
- **Comments say what is happening, not why it is correct.** What each
  array holds, which step of the derivation a block performs. The proof
  stays on the page; no comments on input reading or print loops.
- Dependency-free (`bits/stdc++.h` is fine), built with
  `g++ -O2 -std=c++17`. Fast IO when the editorial calls out huge input.
- **Verify against the whole test suite, not the samples**: run every
  `tests/**/*.in` and diff against the sibling `.a` answer file. A
  sample-only check stays green while a format problem hides in a big test.

## HTML rules

- Math is KaTeX: `\(...\)` and `\[...\]` (`$...$` and `$$...$$` also
  work). The complexity block is the theme's `.complexity` **div** — never
  `<pre class="complexity">`, where the math will not render.
- Restatement highlights are `<mark>`; diagrams are inline SVG or `<pre>`
  ASCII, with no extra libraries; escape `<` and `&` in user-facing text.
- **No algorithm box.** No pseudocode, and do not paste `sol-main.cpp`
  into the page. A displayed recurrence or matrix is fine; the last step
  of the derivation should make the method obvious on its own.
- One continuous scroll: no slide framework, no pager, no "next page"
  control. Keep the print stylesheet as it is (`@page { margin: 0 }`, so
  PDF pages join and the inset comes from `.page` padding).
- The theme's tokens are a tribute; do not brand the page with them.

## Done

- [ ] This conversation explicitly asked for an editorial
- [ ] `$PROBLEM/editorial/editorial.html` opens standalone from the
      filesystem — one scroll, no server, no sibling files
- [ ] Chat led with the expected difficulty; same plain number, no `*`,
      in the header
- [ ] Restatement cross-checked against the statement / `problem.json`:
      subtask points, output format, problem-defining guarantees
- [ ] Lore stripped; load-bearing facts `<mark>`ed; identifiers keep case
- [ ] Every Observation on the page is pivotal — removing it would break
      the derivation — and no box is labelled Transformation
- [ ] Every state defined, every transition derived, every formula's terms
      explained; no trailing paragraph restating a proof already given
- [ ] Complexity is a `.complexity` div with KaTeX, and the page says
      where the bound comes from
- [ ] No pseudocode box, no setter asides, no fun fact unless asked
- [ ] Subtasks: sections only if the problem has them, each with its own
      complexity; no OI / IOI / ICPC label and no "there are no subtasks"
- [ ] Vietnamese, if asked: glossary read, `lang="vi"`, đơn đồ thị, Yêu
      cầu above Giới hạn, chrome still in English
- [ ] Whole-contest page, if asked: TOC, one `section.problem` each, no
      iframes, and both copies carry every fix
- [ ] `sol-editorial.cpp`, if asked: matches the prose, compiles, agrees
      with every `.a` in `tests/`
