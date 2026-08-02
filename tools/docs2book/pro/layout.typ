#import "@preview/hydra:0.6.3": hydra

#show selector.or(pagebreak.where(to: "odd"), pagebreak.where(to: "even")): set page(header: none, footer: none)

#let gutter-for(pages) = {
  if pages <= 150 {
    9.6mm
  } else if pages <= 300 {
    12.7mm
  } else if pages <= 500 {
    15.9mm
  } else {
    19.1mm
  }
}

#let page-setup(pages: 200, trim: "us-trade") = {
  set page(
    paper: trim,
    margin: (
      inside: gutter-for(pages),
      outside: 12.7mm,
      top: 19mm,
      bottom: 19mm,
    ),
    binding: left,
  )
}

#let front-matter-numbering() = {
  set page(numbering: "i")
}

#let body-numbering() = {
  set page(numbering: "1")
  counter(page).update(1)
}

#let running-header(book-title) = context {
  hydra(1)
}
