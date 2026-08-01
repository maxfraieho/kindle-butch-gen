#set document(title: "TITLE_PLACEHOLDER", author: "AUTHOR_PLACEHOLDER")
#set text(font: "Liberation Serif", lang: "LANG_PLACEHOLDER", size: 10.5pt, hyphenate: true)
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
