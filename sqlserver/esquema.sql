-- Esquema SQLite compartido por la API y Jeveador.
-- Ejecutar sobre el archivo de base de datos indicado por CADENA.
-- Las tablas existentes y sus datos se conservan; no realiza migraciones.
-- Se puede volver a ejecutar sin duplicar ni sobrescribir los datos iniciales.

BEGIN IMMEDIATE;

-- Catálogo de descripciones utilizado por Swagger al iniciar la API.
CREATE TABLE IF NOT EXISTS errores (
    codigo INTEGER PRIMARY KEY,
    descripcion TEXT NOT NULL
);

INSERT INTO errores (codigo, descripcion) VALUES
    (502, 'Error de OpenAI, del MCP o de sus respuestas.'),
    (503, 'Falta la clave de OpenAI.'),
    (504, 'Tiempo de espera agotado.')
ON CONFLICT(codigo) DO NOTHING;

-- Consumos de OpenAI y Jev. Las fechas se almacenan en UTC.
CREATE TABLE IF NOT EXISTS billing (
    id INTEGER PRIMARY KEY,
    fecha_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    input_tokens INTEGER,
    cached_tokens INTEGER,
    cache_write_tokens INTEGER,
    output_tokens INTEGER,
    reasoning_tokens INTEGER,
    total_tokens INTEGER,
    costo_estimado_usd REAL,
    metodo TEXT,
    herramientas TEXT NOT NULL
);

-- Umbral decimal: 0.85 equivale a 85 en la página de Umbral.
CREATE TABLE IF NOT EXISTS config_umbral (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    valor REAL NOT NULL
);

INSERT INTO config_umbral (id, valor) VALUES (1, 0.85)
ON CONFLICT(id) DO NOTHING;

-- Catálogo MCP. Las altas desde la API fijan habilitado = 0 explícitamente.
-- El DEFAULT 1 conserva la definición utilizada por el proyecto.
CREATE TABLE IF NOT EXISTS mcps (
    id INTEGER PRIMARY KEY,
    nombre TEXT NOT NULL UNIQUE,
    url TEXT NOT NULL,
    habilitado INTEGER NOT NULL DEFAULT 1 CHECK (habilitado IN (0, 1))
);

-- Agregar los MCPs desde la página MCPs y habilitarlos cuando corresponda.
-- El catálogo queda vacío en una base nueva. No se repueblan MCPs eliminados.

COMMIT;
