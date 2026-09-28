// One-time mechanical migration and ongoing checks; layout declarations stay local.
const fs = require('node:fs')
const path = require('node:path')
const postcss = require('postcss')
const values = require('postcss-value-parser')
const root = path.resolve(__dirname, '../..')
const apply = process.argv.includes('--write')
const check = process.argv.includes('--check')
const tokensFile = path.join(root, 'shared/ui/tokens.css')
const palette = []
const tokenNames = new Set()
postcss.parse(fs.readFileSync(tokensFile, 'utf8')).walkDecls(decl => {
  tokenNames.add(decl.prop)
  if (decl.prop.startsWith('--ui-') && /^#[0-9a-f]{6}$/i.test(decl.value)) {
    palette.push({ name: decl.prop, rgb: [1, 3, 5].map(index => parseInt(decl.value.slice(index, index + 2), 16)) })
  }
})
const textSizes = [11, 12, 13, 14, 16, 18, 20, 24, 28, 32, 40]
const visual = /^(color|background(?:-color|-image)?|border(?:-.+)?|outline(?:-.+)?|box-shadow|text-shadow|font(?:-.+)?|letter-spacing|line-height|accent-color|fill|stroke)$/
const count = { files: 0, colors: 0, typography: 0, radii: 0, gradients: 0, important: 0 }
const failures = []

function luminance(rgb) {
  const linear = rgb.map(channel => channel / 255).map(channel => channel <= .04045 ? channel / 12.92 : ((channel + .055) / 1.055) ** 2.4)
  return linear[0] * .2126 + linear[1] * .7152 + linear[2] * .0722
}

if (check) {
  const pairs = [['on-primary', 'primary'], ['on-primary', 'accent'], ['text', 'surface'],
    ['muted', 'surface-alt'], ['success', 'success-soft'], ['warning', 'warning-soft'],
    ['danger', 'danger-soft'], ['info', 'info-soft']]
  for (const [foreground, background] of pairs) {
    const l = [foreground, background].map(name => luminance(palette.find(item => item.name === `--ui-${name}`).rgb))
    const contrast = (Math.max(...l) + .05) / (Math.min(...l) + .05)
    if (contrast < 4.5) failures.push(`Shared theme: ${foreground}/${background} contrast ${contrast.toFixed(2)} is below 4.5`)
  }
}

function files(directory) {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap(entry => {
    const file = path.join(directory, entry.name)
    return entry.isDirectory() ? files(file) : /\.(css|scss)$/.test(file) ? [file] : []
  })
}

function protectedDeclaration(decl) {
  for (let node = decl.parent; node; node = node.parent) {
    if (node.type === 'atrule' && node.name === 'media' && /\bprint\b/.test(node.params)) return true
    if (node.type === 'rule' && /\[data-document-format\]|\.print-document\b|\.document-sheet\b/.test(node.selector)) return true
  }
  return false
}

function color(node) {
  if (node.type === 'word' && /^(white|black)$/i.test(node.value)) return node.value.toLowerCase() === 'white' ? [255, 255, 255, 1] : [0, 0, 0, 1]
  if (node.type === 'word' && /^#[a-f\d]{3,8}$/i.test(node.value)) {
    let hex = node.value.slice(1)
    if (hex.length === 3 || hex.length === 4) hex = [...hex].map(c => c + c).join('')
    if (hex.length !== 6 && hex.length !== 8) return null
    return [...[0, 2, 4].map(index => parseInt(hex.slice(index, index + 2), 16)), hex.length === 8 ? parseInt(hex.slice(6), 16) / 255 : 1]
  }
  if (node.type === 'function' && /^(rgb|rgba)$/i.test(node.value)) {
    const words = node.nodes.filter(item => item.type === 'word').map(item => item.value)
    if ((words.length !== 3 && words.length !== 4) || words.some(item => !/^\d*\.?\d+%?$/.test(item))) return null
    return [...words.slice(0, 3).map(item => parseFloat(item) * (item.endsWith('%') ? 2.55 : 1)), words[3] ? parseFloat(words[3]) / (words[3].endsWith('%') ? 100 : 1) : 1]
  }
  return null
}

function tokenColor(rgba, prop) {
  const [r, g, b, alpha] = rgba
  if (!alpha) return 'transparent'
  if (r === 255 && g === 255 && b === 255 && prop === 'color' && alpha === 1) return 'var(--ui-on-primary)'
  const nearest = palette.reduce((best, item) => {
    const distance = item.rgb.reduce((sum, channel, index) => sum + (channel - rgba[index]) ** 2, 0)
    return distance < best.distance ? { ...item, distance } : best
  }, { distance: Infinity })
  return alpha === 1 ? `var(${nearest.name})` : `color-mix(in srgb, var(${nearest.name}) ${Math.round(alpha * 10000) / 100}%, transparent)`
}

function nearest(number, scale) {
  return scale.reduce((best, item) => Math.abs(item - number) < Math.abs(best - number) ? item : best)
}

const sourceFiles = [...files(path.join(root, 'frontend/src')),
  ...(check ? files(path.join(root, 'shared/ui')).filter(file => file !== tokensFile) : [])]
for (const file of sourceFiles) {
  const original = fs.readFileSync(file, 'utf8').replace(/\r\n/g, '\n')
  const css = postcss.parse(original, { from: file })
  const relative = path.relative(root, file)
  css.walkDecls(decl => {
    if (protectedDeclaration(decl)) return
    if (check) {
      values(decl.value).walk(node => {
        if (node.type === 'function' && node.value === 'url') return false
        if (color(node)) failures.push(`${relative}:${decl.source.start.line}: literal color in ${decl.prop}`)
        if (node.type === 'word' && node.value.startsWith('--ui-') && !tokenNames.has(node.value)) failures.push(`${relative}: undefined token ${node.value}`)
      })
      if (decl.prop === 'font-size' && /\d(?:vw|vh)\b/.test(decl.value)) failures.push(`${relative}: viewport-sized typography`)
      if (decl.important && visual.test(decl.prop)) failures.push(`${relative}:${decl.source.start.line}: visual !important bypasses the theme`)
      return
    }
    if (decl.important && visual.test(decl.prop)) { decl.important = false; count.important++ }
    let parsed = values(decl.value)
    const selector = decl.parent.selector || ''
    if (/^background(?:-image)?$/.test(decl.prop) && /gradient\(/.test(decl.value) && !/url\(/.test(decl.value)) {
      const role = /button|primary|submit|sidebar|brand/.test(selector) ? 'primary' : /progress|fill|bar/.test(selector) ? 'accent' : 'surface'
      decl.value = decl.prop === 'background-image' ? 'none' : `var(--ui-${role})`
      count.gradients++
      parsed = values(decl.value)
    }
    parsed.walk(node => {
      if (node.type === 'function' && node.value === 'url') return false
      const rgba = color(node)
      if (rgba) {
        node.type = 'word'; node.value = tokenColor(rgba, decl.prop); delete node.nodes
        count.colors++
        return false
      }
    })
    decl.value = parsed.toString()
    if (decl.prop === 'font-family' && !/^(inherit|var\()/.test(decl.value)) {
      decl.value = /monospace|Consolas/.test(decl.value) ? 'var(--ui-font-mono)' : 'var(--ui-font)'
      count.typography++
    }
    if (decl.prop === 'font-size' && !decl.value.startsWith('var(')) {
      const parts = [...decl.value.matchAll(/(\d*\.?\d+)(px|rem)/g)]
      if (parts.length) {
        const last = parts.at(-1)
        decl.value = `var(--ui-size-${nearest(Number(last[1]) * (last[2] === 'rem' ? 16 : 1), textSizes)})`
        count.typography++
      }
    }
    if (decl.prop === 'font-weight' && /^\d+$/.test(decl.value)) {
      decl.value = `var(--ui-weight-${Number(decl.value) >= 700 ? 'bold' : Number(decl.value) >= 500 ? 'medium' : 'normal'})`
      count.typography++
    }
    if (decl.prop === 'letter-spacing' && decl.value !== '0') decl.value = '0'
    if (decl.prop === 'border-radius' && !decl.value.includes('var(')) {
      const radius = values(decl.value)
      radius.walk(node => {
        if (node.type !== 'word' || !/^\d+(?:\.\d+)?(?:px|rem)$/.test(node.value)) return
        const pixels = parseFloat(node.value) * (node.value.endsWith('rem') ? 16 : 1)
        if (pixels === 0) { node.value = '0'; return }
        node.value = `var(--ui-radius-${pixels <= 4 ? 'sm' : pixels <= 6 ? 'control' : 'panel'})`
        count.radii++
      })
      decl.value = radius.toString()
    }
    if (decl.prop === 'box-shadow' && decl.value !== 'none' && !/inset|var\(--ui-shadow/.test(decl.value)) {
      decl.value = /modal|dialog|popover|dropdown/.test(selector) ? 'var(--ui-shadow-dialog)' : 'var(--ui-shadow-sm)'
    }
  })
  if (check) {
    for (const node of css.nodes) {
      if (node.type === 'rule' || (node.type === 'atrule' && !['import', 'use', 'layer'].includes(node.name))) failures.push(`${relative}: rules outside a cascade layer`)
    }
  } else if (css.nodes.length && !css.nodes.some(node => node.type === 'atrule' && node.name === 'layer')) {
    const nodes = css.nodes.filter(node => !(node.type === 'atrule' && ['import', 'use'].includes(node.name)))
    const layer = postcss.atRule({ name: 'layer', params: 'legacy' })
    for (const node of nodes) { node.remove(); layer.append(node) }
    css.append(layer)
  }
  if (!check) css.walkAtRules('layer', layer => {
    if (layer.params !== 'legacy' || !layer.nodes) return
    layer.nodes.forEach((node, index) => { node.raws.before = index ? '\n\n' : '\n' })
    layer.raws.after = '\n'
  })
  const output = css.toString()
  if (output !== original) { count.files++; if (apply) fs.writeFileSync(file, output) }
}
if (failures.length) { console.error(failures.slice(0, 60).join('\n')); console.error(`${failures.length} style violations`); process.exitCode = 1 }
else console.log(check ? `Unified style checks passed: ${sourceFiles.length} style sheets, shared tokens and cascade layers.` : JSON.stringify(count, null, 2))
