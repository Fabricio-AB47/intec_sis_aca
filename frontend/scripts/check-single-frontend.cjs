const fs = require('node:fs')
const path = require('node:path')
const frontend = path.resolve(__dirname, '..')
const root = path.dirname(frontend)
const pkg = JSON.parse(fs.readFileSync(path.join(frontend, 'package.json'), 'utf8'))
if (fs.existsSync(path.join(root, 'frontend-angular'))) {
  throw new Error('La carpeta frontend-angular no debe existir, ni siquiera vacia o con archivos generados. La aplicacion unificada esta en frontend/.')
}
if (Object.keys({ ...pkg.dependencies, ...pkg.devDependencies }).some(name => name.startsWith('@angular/'))) {
  throw new Error('Solo frontend/React debe ser una aplicacion desplegable. Titulacion comparte su sesion y estilos.')
}
if (!fs.existsSync(path.join(frontend, 'src/features/titulacion/TitulationPortal.tsx'))) {
  throw new Error('Falta el portal de titulacion integrado en React.')
}
console.log('Frontend unico verificado: React, una compilacion y una sesion academica.')
