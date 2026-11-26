// One shared tooltip for the whole page, driven by the `tooltip` action.

class TipState {
  text = $state<string | null>(null)
  x = $state(0)
  top = $state(0)
  bottom = $state(0)
}

export const tip = new TipState()

export function tooltip(node: HTMLElement, text: string | null | undefined) {
  let current = text
  const show = () => {
    if (!current) return
    const r = node.getBoundingClientRect()
    tip.text = current
    tip.x = r.left + r.width / 2
    tip.top = r.top
    tip.bottom = r.bottom
  }
  const hide = () => {
    tip.text = null
  }
  node.addEventListener('mouseenter', show)
  node.addEventListener('mouseleave', hide)
  node.addEventListener('focusin', show)
  node.addEventListener('focusout', hide)
  return {
    update(t: string | null | undefined) {
      current = t
    },
    destroy() {
      hide()
      node.removeEventListener('mouseenter', show)
      node.removeEventListener('mouseleave', hide)
      node.removeEventListener('focusin', show)
      node.removeEventListener('focusout', hide)
    },
  }
}
