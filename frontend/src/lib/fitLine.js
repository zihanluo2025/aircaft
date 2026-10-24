// v-fit-line: show a list of names on one line when they all fit, otherwise one per line --
// all or nothing, never a half-wrapped row. CSS alone can't switch layout on the content's own
// width, so measure it: lay the items out on one line, compare with the space available, and
// toggle the "stacked" class. Re-checks when the width changes (rotation, resize) or the list does.
function check(el) {
  el.classList.remove('stacked')
  // Right-aligned content overflows to the left, which scrollWidth doesn't count -- measure it
  // start-aligned for this one synchronous moment (no paint happens in between).
  el.style.justifyContent = 'flex-start'
  const overflows = el.scrollWidth > el.clientWidth + 1
  el.style.justifyContent = ''
  el.classList.toggle('stacked', overflows)
}

export const vFitLine = {
  mounted(el) {
    let lastWidth = -1
    el._fitObserver = new ResizeObserver(([entry]) => {
      const width = Math.round(entry.contentRect.width)
      if (width === lastWidth) return // only a width change can change the answer; ignore height
      lastWidth = width
      check(el)
    })
    el._fitObserver.observe(el)
    el._fitText = el.textContent
    check(el)
  },
  updated(el) {
    // the parent re-renders often (e.g. a ticking clock); measuring forces a layout, so skip it
    // unless the names themselves changed
    if (el.textContent === el._fitText) return
    el._fitText = el.textContent
    check(el)
  },
  unmounted(el) {
    el._fitObserver?.disconnect()
  },
}
