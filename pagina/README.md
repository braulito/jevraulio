# Chat y costos

Aplicación Flask que consulta `billing` y permite editar `config_umbral`.
No crea tablas ni bases de datos. Costos usa conexiones de solo lectura;
guardar el umbral abre la base existente con permiso de escritura.

Desde esta carpeta, usando el entorno virtual existente:

```powershell
.\pagina\Scripts\python.exe -m pip install -r requirements.txt
.\pagina\Scripts\python.exe app.py
```

Abrir http://127.0.0.1:8000/ para el chat (`/index.html` también sirve la página).
Los costos están en `/costos` y `/costos.html`. Ambas páginas comparten la barra
de navegación definida en `templates/partials/navegacion.html`.
La página `/umbral` (también `/umbral.html`) muestra el valor del registro
`config_umbral.id = 1` multiplicado por 100. Al guardar, divide el porcentaje
por 100 y actualiza únicamente ese registro. Acepta porcentajes de 0 a 100,
incluidos decimales. La tabla y el registro deben existir previamente.

`API_URL` debe contener la URL completa del endpoint `/chat` que recibe
`{"mensaje": "..."}`. Flask envía la consulta desde el servidor, espera hasta
120 segundos y muestra únicamente `respuesta` si la API devuelve HTTP 200 y
`estado` igual a `Ok` (sin distinguir mayúsculas). Cualquier error HTTP, de
conexión o de formato muestra «Ocurrió un error.». El botón se deshabilita
mientras espera para evitar envíos duplicados. Cada consulta es independiente.

`cliente_api.py` contiene la comunicación HTTP; la URL se obtiene de la
configuración local al iniciar la aplicación y no se envía al navegador.

La aplicación carga `CADENA` del archivo de configuración local al iniciarse.
Su valor debe ser la ruta al archivo SQLite existente. Las rutas relativas se
resuelven desde esta carpeta (`pagina`); las absolutas se usan directamente.
Una variable `CADENA` ya definida en el entorno tiene prioridad.

`bases.py` contiene la conexión y la consulta; `app.py` define las rutas.
`templates/index.html` y `templates/costos.html` heredan de `templates/base.html`,
que incluye la barra de navegación compartida.

Las fechas se convierten de UTC a GMT-3 al mostrarlas, los costos en USD con ocho decimales, los tokens
con separadores de miles y los valores nulos con un guion. Todos los registros
se muestran del más reciente al más antiguo, paginados según `PAGINA_SIZE`.
Esta variable debe ser un entero positivo; si falta o es inválida, se usan
50 registros por página. Los controles Anterior y Siguiente cambian el parámetro
`pagina` de la URL. Los costos y tokens se suman por separado para JEV
(`metodo = 'JEV'`) y OpenAI (los demás registros), sobre toda la tabla e
independientemente de la página seleccionada. No se muestra un total combinado.
Los controles «Mostrar consumos» permiten mostrar u ocultar cada grupo, tanto
en la tabla como en su resumen. La selección se conserva al paginar o actualizar;
al cambiarla se vuelve a la primera página. Cada resumen suma el grupo completo.

Para verificaciones automatizadas sin cargar la configuración local, importar
`crear_app` y usar `crear_app(cargar_entorno=False)` con una ruta de prueba en
`app.config["CADENA"]`. No iniciar la aplicación normal para esas verificaciones.
