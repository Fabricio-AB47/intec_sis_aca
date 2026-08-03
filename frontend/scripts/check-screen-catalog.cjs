const fs = require('node:fs')
const path = require('node:path')
const ts = require('typescript')

const repoRoot = path.resolve(__dirname, '..', '..')
const backendCatalogPath = path.join(repoRoot, 'backend', 'app', 'services', 'screen_access.py')
const navigationPath = path.join(repoRoot, 'frontend', 'src', 'components', 'StudentLayout.tsx')

const backendSource = fs.readFileSync(backendCatalogPath, 'utf8')
const navigationSource = fs.readFileSync(navigationPath, 'utf8')

const rootScreens = [...backendSource.matchAll(/_screen\(\s*"([^"]+)"/g)].map((match) => match[1])
const flows = [...backendSource.matchAll(/_flow\(\s*"([^"]+)"\s*,\s*"([^"]+)"/g)].map((match) => ({
  parent: match[1],
  code: `${match[1]}/${match[2]}`,
}))
const containerPages = new Set(flows.map((flow) => flow.parent))
const backendScreens = new Set([
  ...rootScreens.filter((screen) => !containerPages.has(screen)),
  ...flows.map((flow) => flow.code),
])

const sourceFile = ts.createSourceFile(
  navigationPath,
  navigationSource,
  ts.ScriptTarget.Latest,
  true,
  ts.ScriptKind.TSX,
)

function property(node, name) {
  return node.properties.find((candidate) => (
    ts.isPropertyAssignment(candidate)
    && ((ts.isIdentifier(candidate.name) && candidate.name.text === name)
      || (ts.isStringLiteral(candidate.name) && candidate.name.text === name))
  ))
}

function stringValue(expression) {
  let current = expression
  while (
    ts.isAsExpression(current)
    || ts.isTypeAssertionExpression(current)
    || ts.isParenthesizedExpression(current)
    || ts.isSatisfiesExpression(current)
  ) {
    current = current.expression
  }
  return ts.isStringLiteralLike(current) ? current.text : ''
}

const navigationScreens = new Set()

function visit(node) {
  if (ts.isObjectLiteralExpression(node) && property(node, 'action')) {
    const accessCodeProperty = property(node, 'accessCode')
    const pageProperty = property(node, 'page')
    const accessCode = accessCodeProperty ? stringValue(accessCodeProperty.initializer) : ''
    const page = pageProperty ? stringValue(pageProperty.initializer) : ''
    if (accessCode) {
      navigationScreens.add(accessCode)
    } else if (page) {
      const childProperty = property(node, 'sectionKey')
        || property(node, 'reportKey')
        || property(node, 'preinscriptionStage')
      const child = childProperty ? stringValue(childProperty.initializer) : ''
      navigationScreens.add(child ? `${page}/${child}` : page)
    }
  }
  ts.forEachChild(node, visit)
}

visit(sourceFile)

const missingFromNavigation = [...backendScreens].filter((screen) => !navigationScreens.has(screen)).sort()
const missingFromBackend = [...navigationScreens].filter((screen) => !backendScreens.has(screen)).sort()

if (missingFromNavigation.length || missingFromBackend.length) {
  const messages = ['El catalogo de pantallas y la navegacion no coinciden.']
  if (missingFromNavigation.length) {
    messages.push(`Faltan en StudentLayout: ${missingFromNavigation.join(', ')}`)
  }
  if (missingFromBackend.length) {
    messages.push(`Faltan en screen_access.py: ${missingFromBackend.join(', ')}`)
  }
  throw new Error(messages.join('\n'))
}

console.log(`Catalogo de pantallas verificado: ${backendScreens.size} accesos navegables.`)
