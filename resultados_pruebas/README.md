# Resultados de pruebas

Informes HTML estáticos de los controles de MCP y sus regresiones. Abrir `index.html`: cada prueba tiene su archivo `0001_nombre.html`, `0002_nombre.html`, etc., con objetivo, resultado esperado, evidencia, modalidad y límites. El código de las pruebas aisladas queda incluido para revisar qué aserciones se ejecutaron.

No requiere servidor ni dependencias de frontend. Los HTML y sus textos se generan con escape de contenido; no cargan recursos remotos.

## Generación

Desde `api`, con su Python y dependencias instaladas:

```powershell
.\api\Scripts\python.exe ..\resultados_pruebas\generar_informes.py --suite api
```

Desde `jeveador`:

```powershell
.\jeveador\Scripts\python.exe ..\resultados_pruebas\generar_informes.py --suite jeveador
```

Las suites sustituyen la carga de `.env` antes de descubrir las pruebas, usan configuración ficticia y no conectan con servicios ni bases reales. Las políticas y bases de prueba son temporales. Las evidencias se guardan en `.evidencias/`.

Las pruebas de integración son optativas y requieren los componentes ya encendidos. Desde `api`:

```powershell
.\api\Scripts\python.exe tests\pruebas_integracion_viva.py
```

Esta ejecución usa HTTP contra API y Jeveador locales. Las consultas pueden consumir tokens y generar filas de billing. Incluye lectura real de clima y conversión de divisas; no modifica registros MCP ni umbrales de la base real. No importa aplicaciones ni abre archivos `.env`.

Finalmente, desde cualquier carpeta:

```powershell
python ruta\a\resultados_pruebas\generar_informes.py --generar
```

## Alcance

Se distinguen controles determinísticos con datos ficticios y pruebas reales de integración. Una respuesta esperada de rechazo puede aprobar una prueba. Los fallos reales quedan visibles; el generador no los convierte en éxitos. La autenticación administrativa está fuera de alcance. No se afirma inmunidad universal a prompt injection ni se asegura la veracidad de los datos de proveedores.
