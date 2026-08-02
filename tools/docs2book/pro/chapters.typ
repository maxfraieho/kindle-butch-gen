#import "@preview/droplet:0.3.1": dropcap

#let setup-chapter-style(..args) = {
  if args.pos().len() == 0 {
    return doc => setup-chapter-style(doc)
  }
  let body = args.pos().first()
  let is-first-par = state("is-first-par", false)

  show heading.where(level: 1): it => {
    pagebreak(to: "odd", weak: true)
    set page(header: none, footer: none)
    is-first-par.update(true)
    it
  }

  show par: it => context {
    let is-first = is-first-par.get()
    if is-first {
      is-first-par.update(false)
      show par: p => p.body
      dropcap(height: 3, it.body)
    } else {
      it
    }
  }

  body
}
