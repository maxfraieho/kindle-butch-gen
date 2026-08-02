// Book publication quality module (2026-08-02) -- wrapper that ties
// pro/layout.typ, pro/frontmatter.typ and pro/chapters.typ together.
// Consumed by main.typ (see build_book.py's build_typst()), NOT by pandoc
// directly -- pandoc only produces body.typ (a bare markdown->typst
// fragment, no --template), so nothing here needs to be valid Pandoc
// template syntax (no $var$, no escaping concerns for book titles/text
// containing "#", "$", quotes, etc. -- see Phase 0.1 in
// book_publication_quality_implementation_plan.md for why the old
// --template + str.replace approach was replaced).
//
// horizontalrule is exported as a plain top-level binding (not nested
// inside book()) because Pandoc's Typst writer emits a bare
// "#horizontalrule" reference for markdown "---"/"***" directly into
// body.typ. Typst's #include evaluates the included file in ITS OWN
// top-level scope -- it does NOT inherit bindings from the file that
// includes it, unlike a textual/macro-style include -- so build_book.py
// must prepend `#import "pro_book_template.typ": horizontalrule` to the
// top of the pandoc-generated body.typ itself (not main.typ) for this to
// resolve. Verified this the hard way: importing horizontalrule only in
// main.typ, then #include-ing body.typ (whether via `#show: book.with(..)`
// or a direct `#book(..)[ #include "body.typ" ]` call), both failed with
// "unknown variable: horizontalrule" at body.typ's own #horizontalrule
// line -- the import has to live in body.typ's file, not the caller's.
#let horizontalrule = line(start: (25%, 0%), end: (75%, 0%))

#import "pro/layout.typ": page-setup, front-matter-numbering, body-numbering, running-header
#import "pro/frontmatter.typ": half-title, title-page, copyright-page, dedication, toc-page
#import "pro/chapters.typ": setup-chapter-style

// meta keys used here (see book_publication_quality_implementation_plan.md
// section "0.2" for the full schema once ratified): title, subtitle,
// authors, publisher, year, copyright_text, isbn, dedication, toc_title,
// exlibris_path (all -- frontmatter.typ), trim, pages (-- layout.typ).
// Every field frontmatter.typ treats as optional stays optional here too;
// this function does not add its own required-ness on top.
#let book(meta: (:), doc) = {
  let pages = meta.at("pages", default: 200)
  let trim = meta.at("trim", default: "us-trade")
  let lang = meta.at("lang", default: "en")
  let title = meta.at("title", default: "")

  page-setup(pages: pages, trim: trim)
  set text(font: ("Source Serif 4", "Libertinus Serif"), lang: lang, size: 10.5pt, hyphenate: true, number-type: "old-style")
  set par(justify: true, leading: 0.65em, first-line-indent: 1.2em)
  set heading(numbering: "1.1")

  // Carried over unchanged from the original book_template.typ.
  show raw.where(block: true): set block(
    fill: rgb("#f8f9fa"),
    inset: 8pt,
    radius: 3pt,
    stroke: 0.5pt + rgb("#e9ecef"),
  )
  show link: it => {
    if type(it.dest) == str and it.dest.starts-with("http") [
      #it.body #footnote(raw(it.dest))
    ] else [
      #it
    ]
  }
  set table(stroke: 0.5pt + rgb("#cccccc"), inset: (x: 8pt, y: 5pt))
  show table.header: it => { set text(weight: "bold"); it }

  front-matter-numbering()
  half-title(meta)
  title-page(meta)
  copyright-page(meta)
  dedication(meta)
  toc-page(meta)

  body-numbering()
  set page(header: context running-header(title))

  show: setup-chapter-style()
  doc
}
