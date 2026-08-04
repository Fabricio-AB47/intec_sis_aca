const fs = require('node:fs')
const path = require('node:path')
const ts = require('typescript')

const repoRoot = path.resolve(__dirname, '..', '..')
const backendCatalogPath = path.join(repoRoot, 'backend', 'app', 'services', 'screen_access.py')
const navigationPath = path.join(repoRoot, 'frontend', 'src', 'components', 'StudentLayout.tsx')
const appPath = path.join(repoRoot, 'frontend', 'src', 'App.tsx')
const typesPath = path.join(repoRoot, 'frontend', 'src', 'types', 'app.ts')

const backendSource = fs.readFileSync(backendCatalogPath, 'utf8')
const navigationSource = fs.readFileSync(navigationPath, 'utf8')
const appSource = fs.readFileSync(appPath, 'utf8')
const typesSource = fs.readFileSync(typesPath, 'utf8')

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
const appSourceFile = ts.createSourceFile(appPath, appSource, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
const typesSourceFile = ts.createSourceFile(typesPath, typesSource, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS)

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

const pageTypes = new Set()
const renderedPages = new Set()

function collectPageType(node) {
  if (ts.isTypeAliasDeclaration(node) && node.name.text === 'Page') {
    const members = ts.isUnionTypeNode(node.type) ? node.type.types : [node.type]
    members.forEach((member) => {
      if (ts.isLiteralTypeNode(member) && ts.isStringLiteralLike(member.literal)) {
        pageTypes.add(member.literal.text)
      }
    })
  }
  ts.forEachChild(node, collectPageType)
}

function unwrap(expression) {
  let current = expression
  while (
    ts.isAsExpression(current)
    || ts.isTypeAssertionExpression(current)
    || ts.isParenthesizedExpression(current)
    || ts.isSatisfiesExpression(current)
  ) {
    current = current.expression
  }
  return current
}

function isActivePage(expression) {
  const current = unwrap(expression)
  return (ts.isPropertyAccessExpression(current) && current.name.text === 'activePage')
    || (ts.isIdentifier(current) && current.text === 'activePage')
}

function collectRenderedPages(node) {
  if (
    ts.isBinaryExpression(node)
    && [ts.SyntaxKind.EqualsEqualsEqualsToken, ts.SyntaxKind.EqualsEqualsToken].includes(node.operatorToken.kind)
  ) {
    const left = unwrap(node.left)
    const right = unwrap(node.right)
    if (isActivePage(left) && ts.isStringLiteralLike(right)) renderedPages.add(right.text)
    if (isActivePage(right) && ts.isStringLiteralLike(left)) renderedPages.add(left.text)
  }
  ts.forEachChild(node, collectRenderedPages)
}

collectPageType(typesSourceFile)
collectRenderedPages(appSourceFile)

const missingFromNavigation = [...backendScreens].filter((screen) => !navigationScreens.has(screen)).sort()
const missingFromBackend = [...navigationScreens].filter((screen) => !backendScreens.has(screen)).sort()
const rootScreenSet = new Set(rootScreens)
const missingPageTypesFromBackend = [...pageTypes].filter((screen) => !rootScreenSet.has(screen)).sort()
const missingRootScreensFromTypes = [...rootScreenSet].filter((screen) => !pageTypes.has(screen)).sort()
const missingRenderedPages = [...pageTypes].filter((screen) => !renderedPages.has(screen)).sort()

if (
  missingFromNavigation.length
  || missingFromBackend.length
  || missingPageTypesFromBackend.length
  || missingRootScreensFromTypes.length
  || missingRenderedPages.length
) {
  const messages = ['El catalogo, los tipos, las vistas y la navegacion no coinciden.']
  if (missingFromNavigation.length) {
    messages.push(`Faltan en StudentLayout: ${missingFromNavigation.join(', ')}`)
  }
  if (missingFromBackend.length) {
    messages.push(`Faltan en screen_access.py: ${missingFromBackend.join(', ')}`)
  }
  if (missingPageTypesFromBackend.length) {
    messages.push(`Tipos Page sin catalogar: ${missingPageTypesFromBackend.join(', ')}`)
  }
  if (missingRootScreensFromTypes.length) {
    messages.push(`Pantallas raiz sin tipo Page: ${missingRootScreensFromTypes.join(', ')}`)
  }
  if (missingRenderedPages.length) {
    messages.push(`Pantallas Page sin vista en App.tsx: ${missingRenderedPages.join(', ')}`)
  }
  throw new Error(messages.join('\n'))
}

console.log(`Catalogo de pantallas verificado: ${backendScreens.size} accesos navegables y ${pageTypes.size} vistas raiz.`)
