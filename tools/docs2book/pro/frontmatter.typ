// pro/frontmatter.typ

#let half-title(meta) = {
  set page(header: none, footer: none)
  align(center)[
    #v(1fr)
    #text(1.8em, weight: "bold")[#meta.at("title", default: "")]
    #v(2fr)
  ]
  pagebreak(to: "odd")
}

#let title-page(meta) = {
  set page(header: none, footer: none)
  let title = meta.at("title", default: "")
  let subtitle = meta.at("subtitle", default: none)
  let authors = meta.at("authors", default: "")
  let publisher = meta.at("publisher", default: none)
  let year = meta.at("year", default: none)

  align(center)[
    #v(1fr)
    #text(2.2em, weight: "bold")[#title]
    #if subtitle != none and str(subtitle).trim() != "" [
      #v(0.8em)
      #text(1.3em, style: "italic")[#subtitle]
    ]
    #v(2em)
    #text(1.2em)[#authors]
    #v(2fr)
    #if publisher != none and str(publisher).trim() != "" [
      #text(1.1em)[#publisher]
      #if year != none and str(year).trim() != "" [
        \ #text(1em)[#year]
      ]
    ] else if year != none and str(year).trim() != "" [
      #text(1em)[#year]
    ]
  ]
  pagebreak()
}

#let copyright-page(meta) = {
  set page(header: none, footer: none)
  let copyright-text = meta.at("copyright_text", default: "")
  let isbn = meta.at("isbn", default: none)
  let exlibris-path = meta.at("exlibris_path", default: none)

  align(left)[
    #v(1fr)
    #set text(size: 9pt)
    #for paragraph in copyright-text.split("\n\n") {
      if paragraph.trim() != "" [
        #paragraph
        #v(0.6em)
      ]
    }
    #if isbn != none and str(isbn).trim() != "" [
      #v(0.6em)
      #if str(isbn).trim().starts-with("ISBN") [
        #isbn
      ] else [
        ISBN #isbn
      ]
    ]
    #if exlibris-path != none and str(exlibris-path).trim() != "" [
      #v(1em)
      #align(center)[
        #image(exlibris-path, width: 4.5cm)
      ]
    ]
  ]
  pagebreak()
}

#let dedication(meta) = {
  let text-content = meta.at("dedication", default: none)
  if text-content != none and str(text-content).trim() != "" {
    set page(header: none, footer: none)
    align(center)[
      #v(1fr)
      #text(style: "italic")[#text-content]
      #v(2fr)
    ]
    pagebreak(to: "odd")
  }
}

#let toc-page(meta) = {
  set page(header: none, footer: none)
  let title = meta.at("toc_title", default: "Зміст")
  outline(title: title, indent: auto)
  pagebreak(to: "odd")
}
