# Monitor de precios de alimentos en Chile

**Demo:** [precio-alimentos-chile.netlify.app](https://precio-alimentos-chile.netlify.app/)

Panel estático para explorar precios semanales de alimentos publicados por la
[Oficina de Estudios y Políticas Agrarias (ODEPA)](https://datos.odepa.gob.cl/dataset/precios-consumidor).
Incluye referencias por punto de monitoreo, variaciones recientes, un catálogo
filtrable y el historial de cada producto. En las fichas, la serie puede
compararse con el IPC general como referencia de inflación; no es una estimación
de las causas de los cambios de precio.

## Datos y metodología

- Los precios se actualizan desde los recursos públicos de ODEPA. El panel
  muestra la semana más reciente disponible y la fecha de actualización.
- “Nacional” promedia las regiones que informaron datos, dando el mismo peso a
  cada región; no es una canasta ponderada ni un IPC.
- La cobertura histórica comienza en 2017. El año 2019 se excluye por una
  inconsistencia en el recurso anual de ODEPA. En 2021 se omiten dos registros
  de huevos con mínimo mayor que máximo; otras filas inválidas detienen la
  actualización en vez de corregirse silenciosamente.
- Las series de IPC son mensuales y se publican por separado de los precios de
  ODEPA. La interfaz identifica su fuente y período de cobertura.

El navegador solo lee archivos JSON estáticos; no hay backend ni credenciales
de usuario. La base SQLite de trabajo es una caché reconstruible y no se publica.

## Ejecutar localmente

Requisitos: Python 3.11 o superior e internet para descargar datos. El pipeline
usa la biblioteca estándar de Python, sin paquetes externos.

Para reconstruir las fuentes históricas y generar los archivos del sitio:

```sh
python3 pipeline/fetch_odepa.py --full-refresh
```

Las siguientes ejecuciones normales solo vuelven a procesar recursos anuales
que hayan cambiado:

```sh
python3 pipeline/fetch_odepa.py
```

La base local queda en `data/prices.db`; los archivos JSON publicados quedan en
`site/data/`. Para previsualizar el sitio:

```sh
python3 -m http.server 8000 --directory site
```

Abre <http://localhost:8000>.

## Pruebas

Las pruebas usan fixtures pequeños, son deterministas y no consultan ODEPA:

```sh
python3 -m unittest discover -s tests -v
```

## Actualización y despliegue

GitHub Actions ejecuta el refresco los lunes a las 12:00 de `America/Santiago`.
También se puede iniciar manualmente desde la rama por defecto, con o sin
reconstrucción histórica completa. Si la fuente y sus validaciones pasan, el
workflow publica un commit cuando cambian los JSON de `site/data/`; Netlify
despliega `site/` desde `main` mediante su integración con GitHub. La caché
SQLite es prescindible y se puede reconstruir desde ODEPA; no se requieren
secretos de Netlify en GitHub Actions.

## Atribución y licencias

El código y la documentación originales de este proyecto se publican bajo la
licencia [MIT](LICENSE), con copyright de Sebastián Ramírez (2026). Esta licencia
no reemplaza ni modifica las condiciones de los datos, marcas u otros materiales
de terceros que se mencionan o distribuyen junto al software.

- **Precios de ODEPA:** la ficha del conjunto de datos declara Creative Commons
  Attribution. El índice generado conserva la atribución, la procedencia y el
  enlace a la [ficha de ODEPA](https://datos.odepa.gob.cl/dataset/groups/precios-consumidor).
  Las transformaciones y exclusiones aplicadas se documentan en la interfaz y
  en los metadatos publicados.
- **IPC:** el snapshot identifica la serie general empalmada y sus fuentes
  [INE y Banco Central](https://si3.bcentral.cl/siete/ES/Siete/Cuadro/CAP_PRECIOS/MN_CAP_PRECIOS/PEM_IND_IPC_2023?idSerie=G073.IPC.IND.2023.M).
  El Banco Central permite reproducir, publicar y adaptar la información con
  atribución, y pide verificar la fuente original cuando los datos provienen de
  otra institución. El INE declara una licencia CC BY-SA 4.0 para su información.
  Por eso, el snapshot de IPC no queda cubierto por la MIT del software: conserva
  su procedencia y debe reutilizarse respetando las condiciones aplicables de
  sus fuentes.

Revisa las [condiciones de uso del Banco Central](https://si3.bcentral.cl/estadisticas/Principal1/Web_Services/terminos_condiciones.html)
y la [licencia de datos abiertos del INE](https://www.ine.gob.cl/terminos-de-uso-y-licencia-de-datos-abiertos)
antes de redistribuir los datos o sus adaptaciones.
