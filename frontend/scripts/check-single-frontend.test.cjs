const assert = require('node:assert/strict')
const { spawnSync } = require('node:child_process')
const fs = require('node:fs')
const path = require('node:path')
const test = require('node:test')

const logs = path.resolve(__dirname, '../../.runlogs')

function fixture(t, { angularDirectory, dependencies = {}, devDependencies = {}, portal = true } = {}) {
  fs.mkdirSync(logs, { recursive: true })
  const root = fs.mkdtempSync(path.join(logs, 'frontend-structure-'))
  t.after(() => {
    const resolved = fs.realpathSync(root)
    assert.equal(path.dirname(resolved), fs.realpathSync(logs))
    assert.ok(path.basename(resolved).startsWith('frontend-structure-'))
    fs.rmSync(resolved, { recursive: true, force: true })
  })
  const frontend = path.join(root, 'frontend')
  const scripts = path.join(frontend, 'scripts')
  fs.mkdirSync(scripts, { recursive: true })
  fs.copyFileSync(path.join(__dirname, 'check-single-frontend.cjs'), path.join(scripts, 'check-single-frontend.cjs'))
  fs.writeFileSync(path.join(frontend, 'package.json'), JSON.stringify({ dependencies, devDependencies }))
  if (portal) {
    const directory = path.join(frontend, 'src/features/titulacion')
    fs.mkdirSync(directory, { recursive: true })
    fs.writeFileSync(path.join(directory, 'TitulationPortal.tsx'), 'export {}')
  }
  if (angularDirectory) {
    const directory = path.join(root, 'frontend-angular')
    fs.mkdirSync(directory)
    if (angularDirectory === 'generated') fs.mkdirSync(path.join(directory, '.angular'))
    if (angularDirectory === 'application') fs.writeFileSync(path.join(directory, 'package.json'), '{}')
  }
  return spawnSync(process.execPath, [path.join(scripts, 'check-single-frontend.cjs')], { encoding: 'utf8' })
}

test('accepts the integrated frontend without a secondary directory', t => {
  const result = fixture(t, { dependencies: { react: '19', 'react-dom': '19' } })
  assert.equal(result.status, 0, result.stderr)
  assert.match(result.stdout, /Frontend unico verificado/)
})

for (const angularDirectory of ['empty', 'generated', 'application']) {
  test(`rejects a secondary directory: ${angularDirectory}`, t => {
    const result = fixture(t, { angularDirectory })
    assert.equal(result.status, 1)
    assert.match(result.stderr, /La carpeta frontend-angular no debe existir/)
  })
}

for (const field of ['dependencies', 'devDependencies']) {
  test(`rejects Angular in ${field}`, t => {
    const result = fixture(t, { [field]: { '@angular/core': '1' } })
    assert.equal(result.status, 1)
    assert.match(result.stderr, /Solo frontend\/React/)
  })
}

test('requires the integrated titulation portal', t => {
  const result = fixture(t, { portal: false })
  assert.equal(result.status, 1)
  assert.match(result.stderr, /Falta el portal de titulacion integrado/)
})
