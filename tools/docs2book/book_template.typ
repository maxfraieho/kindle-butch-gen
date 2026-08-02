#let horizontalrule = line(start: (25%,0%), end: (75%,0%))
#set document(title: "TITLE_PLACEHOLDER", author: "AUTHOR_PLACEHOLDER")
// Book publication quality research (2026-08-02): Liberation Serif was never
// actually installed on this device (Typst silently fell back to Libertinus
// Serif for every book rendered before this fix -- build_book.py's
// build_typst() only printed stderr on a non-zero exit code, hiding the
// "unknown font family" warning). Source Serif 4 (SIL OFL, installed to
// ~/.local/share/fonts, exposed via build_typst()'s new --font-path) has
// stronger Cyrillic support for this bilingual EN/UK content; Libertinus
// Serif (one of Typst's 4 built-in fonts) is the fallback if it's ever
// missing on a given machine, so this stays renderable either way.
#set text(font: ("Source Serif 4", "Libertinus Serif"), lang: "LANG_PLACEHOLDER", size: 10.5pt, hyphenate: true, number-type: "old-style")
#set par(justify: true, leading: 0.65em, first-line-indent: 1.2em)
#set heading(numbering: "1.1")
#set page(
  paper: "a4",
  margin: (top: 2.5cm, bottom: 2.5cm, left: 3cm, right: 2cm),
)

#show raw.where(block: true): set block(
  fill: rgb("#f8f9fa"),
  inset: 8pt,
  radius: 3pt,
  stroke: 0.5pt + rgb("#e9ecef"),
)

#show link: it => {
  if type(it.dest) == str and it.dest.starts-with("http") [
    #it.body #footnote(raw(it.dest))
  ] else [
    #it
  ]
}

#set table(stroke: 0.5pt + rgb("#cccccc"), inset: (x: 8pt, y: 5pt))
#show table.header: it => { set text(weight: "bold"); it }

#align(center + horizon)[
  #text(size: 30pt, weight: "bold")[TITLE_PLACEHOLDER]
  #v(1em)
  #line(length: 40%, stroke: 1.5pt)
  #v(1em)
  #text(size: 14pt, style: "italic")[AUTHOR_PLACEHOLDER]
]
#pagebreak()

#outline(title: "OUTLINE_TITLE_PLACEHOLDER", indent: auto)
#pagebreak()

$body$
