# Import formats

## Block format

The default. Cards are separated by a line with three or more dashes (`---`). Each field starts with `Name:` and can continue over several lines.

```text
# deck: Physics::Electromagnetism
# type: basic
# tags: maxwell em

Front: Gauss's law (differential form)
Back: $$\divg\vb{E} = \frac{\rho}{\varepsilon_0}$$
Extra: Follows from the integral form via the divergence theorem.
---
Front: Faraday's law
Back:
$$
\curl\vb{E} = -\pdv{\vb{B}}{t}
$$
Tags: induction
```

### Header directives (optional, at the top)

| Directive | Meaning |
| --- | --- |
| `# deck: Name::Sub` | Deck name. `::` makes subdecks. |
| `# type: basic` | `basic`, `reversed`, `cloze` or `custom`. If omitted, it's inferred from the field names. |
| `# tags: a b c` | Tags added to every card. |
| `# fields: Term, Formula, Units` | Declares the field names. Only these names (plus `Tags`) start a new field, so prose like `Note: …` inside an answer won't split it. |

### Fields

- Field names are case-insensitive (`front:` = `Front:`).
- Built-in types use **Front / Back / Extra** (basic, reversed) or **Text / Extra** (cloze).
- Any other names make a **custom** note type: the first field is the question side and the rest go on the answer side.
- `Tags: x y` on a card adds tags to that card only.
- A line like `Something:` inside an open `$$ … $$` block is treated as math, not a new field.

### Cloze

```text
# type: cloze
Text: Newton's second law: {{c1::$\vb{F} = m\vb{a}$}}, valid in {{c2::inertial}} frames.
Extra: Optional notes.
```

## Delimited format

One card per line. The separator can be tab (default), `|`, `;` or `,`. Choose the column → field mapping in the Import view, or with `--fields` on the CLI. Quoted values work as in CSV. Write `\n` for a line break inside a field. Lines starting with `#` are skipped, so Anki's own exports (`#separator:tab` …) import directly.

```text
Speed of light	$c = 299\,792\,458\ \mathrm{m/s}$
de Broglie wavelength	$\lambda = h/p$
```

## LaTeX

| You write | Anki gets |
| --- | --- |
| `$x^2$` | `\(x^2\)` (inline) |
| `$$\int f\,dx$$` | `\[\int f\,dx\]` (display) |
| `\$5` | a literal `$5` |
| `` `$code$` `` | left untouched |

Built-in physics macros (editable under **Settings → LaTeX macros**):

| Macro | Expands to |
| --- | --- |
| `\vb{E}` | **E** (bold vector) |
| `\vu{r}` | unit vector r̂ |
| `\dv{x}{t}` | dx/dt |
| `\pdv{f}{x}` | ∂f/∂x |
| `\abs{x}`, `\norm{v}` | \|x\|, ‖v‖ |
| `\ev{A}` | ⟨A⟩ |
| `\bra{a}`, `\ket{b}`, `\braket{a}{b}` | Dirac notation |
| `\grad`, `\curl`, `\divg` | ∇, ∇×, ∇· |

`\ce{…}` (mhchem) works in the preview and in Anki 2.1.50+.

Macros are copied into each card template as a hidden `\newcommand` block, so they render on Anki desktop, AnkiWeb and AnkiDroid/AnkiMobile without any add-ons.
