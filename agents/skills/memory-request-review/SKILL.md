---
name: memory-request-review
description: "Use when reviewing pending Hermes memory or skill writes across default, implementer, and reviewer. Inventory native requests, evaluate and show one ASCII dashboard at a time, and require an explicit human decision."
---

# Revisión asistida de solicitudes de memoria

Usa esta skill al iniciar una conversación nueva para revisar los pendientes
nativos de `memory` y `skills` de los perfiles `default`, `implementer` y
`reviewer`. No crea ni mantiene otra cola: Hermes sigue siendo la única fuente
de pendientes y el único mecanismo que puede aplicar una decisión.

## Límites de autoridad

- No apruebes ni rechaces por una probabilidad, por falta de señales ni por un
  error de Jev.
- No modifiques una solicitud pendiente, no separes sus operaciones y no
  reconstruyas una escritura con herramientas de archivo o memoria.
- No envíes conversaciones, memorias actuales, skills instaladas ni resúmenes a
  Jev. El único estado remoto permitido es el objeto literal `payload` del
  pendiente nativo.
- Si el panel muestra `RETENIDA LOCALMENTE`, no expongas ni copies el valor
  detectado y no lo envíes a Jev. Explica que el detector puede tener falsos
  positivos y negativos.
- Con `SIN CRITERIOS`, no llames a Jev ni inventes puntuaciones: inicia revisión
  humana de casos reales.

## Inicio de lote

`./bootstrap` prepara el entorno con la versión fija de `typesafe-sdk` declarada
en `requirements.txt`. El script de revisión lo descubre automáticamente desde
su ubicación, independientemente del directorio actual y de los enlaces de
skills. No pidas exportar variables ni interpretes una variable ausente como
una instalación faltante. `HERMES_MEMORY_REVIEW_PYTHON` es solo una selección
explícita opcional de otro intérprete preparado. No instales dependencias al
ejecutar una revisión; si falta el entorno, indica que se ejecute bootstrap.

```sh
python3 \
  agents/skills/memory-request-review/scripts/review_memory_requests.py inventory
```

Informa los conteos de `memory`, `skills` y registros ilegibles. Los registros
ilegibles no son aprobables; déjalos pendientes y muestra su identidad/error.

Revisa una solicitud a la vez. `show` envía a Jev solo la solicitud indicada
(las demás esperan su turno) y renderiza su panel ya evaluado; no hay un paso
previo de mostrar la propuesta y después evaluarla.

```sh
python3 \
  agents/skills/memory-request-review/scripts/review_memory_requests.py show \
  --position 1
```

Copia el panel dentro de un bloque de código, sin comentarios añadidos ni
JSON. Para la vista humana, muestra solo el nombre del perfil en la cabecera
y oculta identificadores técnicos (`pending-id`, `record_sha256`,
`payload_sha256`). Conserva esos valores de forma interna para `decide`.
El panel enseña `Target` (`memory`, `user` o `skill:<nombre>`), cada operación
como `ADD`, `DELETE` o `REPLACE` con su texto (`−` anterior, `+` nuevo) sin
detallar en qué parte del archivo cae, y cada pregunta de Jev con su
probabilidad (mayor = problema más probable). No uses medias ni conviertas
resultados en una nota de calidad. Muestra como máximo una solicitud por turno.

## Decisión por solicitud

Tras enseñar exactamente un panel, ofrece: **aprobar**, **rechazar**, **dejar
pendiente** o **discutir/proponer criterio**. Avanzar no es una decisión.

Solo después de que la persona responda explícitamente `aprobar` o `rechazar`,
usa la identidad y el `record_sha256` capturados al revisar la solicitud:
perfil, subsistema e ID nativo. No elijas de nuevo por posición. El hash evita
actuar sobre un pendiente modificado, reemplazado o ya resuelto:

```sh
python3 \
  agents/skills/memory-request-review/scripts/review_memory_requests.py decide \
  --profile default --subsystem memory --pending-id '<id-revisado>' \
  --decision approve --human-decision \
  --expected-record-sha256 '<hash-mostrado-al-revisar>'
```

Usa `--decision reject` para rechazar. Verifica la respuesta: `success: true`,
`pending_removed: true` y, para una aprobación, el `native_result` de Hermes.
Si falla o el hash cambió, no intentes reparar, volver a crear ni aplicar una
variante; vuelve a inventariar y solicita nueva revisión.

## Aprendizaje de criterios

Las preguntas que se envían a Jev viven solo en:

```text
agents/skills/memory-request-review/criteria.json
```

Toda edición de `criteria.json` (agregar, reformular, versionar o eliminar un
criterio, o cambiar `catalog_version`) requiere la aprobación explícita de una
persona sobre el texto exacto del cambio antes de escribirlo. Muestra el diff
propuesto y espera un `sí` explícito; una propuesta tuya, una puntuación de Jev
o una aprobación previa de otro cambio no cuentan como aprobación.

Después de un rechazo, pregunta si el caso justifica una condición general. No
la agregues por inferencia.

Cada criterio aprobado requiere `id`, `version`, `question`, `context`,
`definition.yes`, `definition.no`, y, si aportan claridad, `exclusions` y
`examples`. Formula una sola condición por pregunta y mantén la dirección:
probabilidad mayor = mayor probabilidad del problema descrito. Aumenta `version`
si cambia el significado.

Después de añadir o cambiar un criterio, vuelve a mostrar/evaluar todos los
pendientes restantes. No reutilices resultados si cambió el payload, la versión
del criterio o la identidad efectiva del modelo. Mantén anteriores únicamente
cuando coincidan las cuatro dimensiones.

## Verificación

Ejecuta las pruebas aisladas antes de declarar la entrega verificada:

```sh
"${HERMES_MEMORY_REVIEW_PYTHON:-.agents/memory-review/bin/python}" \
  agents/skills/memory-request-review/tests/test_review_memory_requests.py
```

La prueba real de Jev exige al menos un criterio aprobado, una solicitud elegible
y `TYPESAFE_API_KEY`, en el entorno o en el `.env` ignorado de la raíz del
checkout (ver `.env.example`); el entorno tiene prioridad. Si faltan,
declara ese bloqueo; nunca simules una evaluación. La integración nativa debe
probarse con un `HERMES_HOME` temporal, nunca aprobando o rechazando pendientes
reales para cobertura.
