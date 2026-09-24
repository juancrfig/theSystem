---
name: memory-request-review
description: "Use when reviewing pending Hermes memory or skill writes across default, implementer, and reviewer. Inventory native requests, show one ASCII panel at a time, and require an explicit human decision."
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

Antes de iniciar, aprovisiona fuera de esta skill un intérprete con una versión
fijada de `typesafe-sdk` declarada en `requirements.txt` y expórtalo como
`HERMES_MEMORY_REVIEW_PYTHON`. No instales dependencias al ejecutar una
revisión.

```sh
"$HERMES_MEMORY_REVIEW_PYTHON" \
  agents/skills/memory-request-review/scripts/review_memory_requests.py inventory
```

Informa los conteos de `memory`, `skills` y registros ilegibles. Los registros
ilegibles no son aprobables; déjalos pendientes y muestra su identidad/error.

Para preparar el lote, muestra la primera solicitud. Cada ejecución de `show`
evalúa todos los pendientes elegibles del inventario actual antes de renderizar
solo la posición indicada. Conserva los paneles resultantes en la conversación y
no muestres más de una solicitud por turno.

```sh
"$HERMES_MEMORY_REVIEW_PYTHON" \
  agents/skills/memory-request-review/scripts/review_memory_requests.py show \
  --position 1
```

El panel muestra perfil, subsistema, ID, operaciones literales, estado,
identidad de modelo cuando existe, versión de catálogo y cada probabilidad. No
uses medias ni conviertas resultados en una nota de calidad.

## Decisión por solicitud

Tras enseñar exactamente un panel, ofrece: **aprobar**, **rechazar**, **dejar
pendiente** o **discutir/proponer criterio**. Avanzar no es una decisión.

Solo después de que la persona responda explícitamente `aprobar` o `rechazar`,
usa la identidad y el `record_sha256` que se mostraron al revisar la solicitud:
perfil, subsistema e ID nativo. No elijas de nuevo por posición. El hash evita
actuar sobre un pendiente modificado, reemplazado o ya resuelto:

```sh
"$HERMES_MEMORY_REVIEW_PYTHON" \
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

Después de un rechazo, pregunta si el caso justifica una condición general. No
la agregues por inferencia. Si la persona acepta explícitamente, edita solo el
catálogo JSON delimitado en:

```text
agents/rules/memory-request-review-catalog.md
```

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
"$HERMES_MEMORY_REVIEW_PYTHON" \
  agents/skills/memory-request-review/tests/test_review_memory_requests.py
```

La prueba real de Jev exige al menos un criterio aprobado, una solicitud elegible
y credenciales de TypeSafe disponibles mediante su mecanismo normal. Si faltan,
declara ese bloqueo; nunca simules una evaluación. La integración nativa debe
probarse con un `HERMES_HOME` temporal, nunca aprobando o rechazando pendientes
reales para cobertura.
