# Revision asistida de solicitudes de memoria con Jev

Status: ready-for-agent
Jira: (none)
Local ticket: issues/01-memory-request-review.md

## Problem Statement

Las propuestas de aprendizaje de Hermes abarcan tanto los archivos de memoria y perfil del usuario como las skills. Sus permisos de escritura dejan solicitudes pendientes cuya revision depende del usuario. Leerlas y evaluar su calidad individualmente constituye un cuello de botella.

Se necesita conservar el control humano y el flujo nativo de aprobacion/rechazo, pero facilitar la revision mediante criterios explicitos que crezcan a partir de decisiones reales. No se pretende repetir el trabajo del auxiliar que extrae aprendizajes de las conversaciones.

## Solution

Crear una skill global de revision, invocable bajo demanda en una conversacion nueva. Recopilara todos los pendientes de los perfiles `default`, `implementer` y `reviewer`, tanto de memoria como de skills, ejecutara las evaluaciones de Jev y presentara cada solicitud por separado mediante un panel ASCII sencillo y legible.

Una regla global sera la fuente de verdad del catalogo de condiciones malas. Cada condicion se expresara como una pregunta Noul con su definicion, contexto y limites. Todas las preguntas aplicables se enviaran juntas por solicitud. El contenido evaluado sera la solicitud literal, sin conversaciones, memorias existentes ni contexto recuperado adicional.

El usuario decidira si aprobar, rechazar, dejar pendiente o discutir una solicitud. Podra confirmar un criterio nuevo a partir de un caso real. La skill actualizara la regla solo con esa autorizacion y evaluara el criterio nuevo sobre todas las solicitudes restantes. Ningun resultado de Jev autoriza una escritura o rechazo automatico.

## User Stories

1. Como usuario, quiero iniciar la revision invocando una skill en una conversacion nueva para no depender del contexto de una sesion anterior.
2. Como usuario, quiero ver el inventario de pendientes de los tres perfiles seleccionados para no revisar solo el perfil activo por accidente.
3. Como usuario, quiero distinguir solicitudes de archivos de memoria, perfil del usuario y skills para entender su destino.
4. Como usuario, quiero que cada solicitud conserve su perfil e identificador nativo para actuar sobre el pendiente correcto.
5. Como usuario, quiero que todos los pendientes del lote se evaluen antes de la revision individual para disponer de sus resultados durante la conversacion.
6. Como usuario, quiero enviar a Jev la propuesta literal para no alterar lo que el auxiliar quiso guardar.
7. Como usuario, quiero que no se envien conversaciones ni otras memorias para limitar el alcance y la exposicion de datos.
8. Como usuario, quiero que las propuestas con posibles credenciales se retengan localmente para evitar su envio al proveedor.
9. Como usuario, quiero una pregunta Noul por patron malo para entender cada senal por separado.
10. Como usuario, quiero aportar definiciones, exclusiones y ejemplos a cada pregunta para que un criterio sea preciso sin hacer ambigua su formulacion.
11. Como usuario, quiero que todas las preguntas independientes de una solicitud se ejecuten juntas para evitar llamadas secuenciales innecesarias.
12. Como usuario, quiero un panel ASCII claro por solicitud para leer su identidad, contenido y resultados sin ruido visual.
13. Como usuario, quiero ver probabilidades por criterio sin una nota promedio para que una infraccion no quede oculta por otros resultados.
14. Como usuario, quiero que un resultado sin senales siga requiriendo mi aprobacion para no confundir ausencia de deteccion con correccion.
15. Como usuario, quiero aprobar o rechazar mediante el flujo nativo de Hermes para no mantener otra cola ni otro sistema de permisos.
16. Como usuario, quiero mantener juntas las operaciones de una solicitud para no separar un borrado de su reemplazo.
17. Como usuario, quiero dejar una solicitud pendiente y continuar para no estar obligado a resolver una duda inmediatamente.
18. Como usuario, quiero decidir si un rechazo justifica una nueva condicion general para evitar convertir cada incidente en una regla.
19. Como usuario, quiero comenzar revisando casos reales cuando el catalogo este vacio para no inventar criterios ni resultados iniciales.
20. Como usuario, quiero aplicar los criterios nuevos a los pendientes restantes para que la revision no use una politica desactualizada.
21. Como usuario, quiero conservar resultados anteriores validos para no repetir evaluaciones ni incurrir en costes innecesarios.
22. Como usuario, quiero distinguir un error del servicio de una evaluacion favorable para no aprobar por ausencia de resultados.
23. Como usuario, quiero que una solicitud modificada o resuelta por otra sesion se detecte antes de actuar para no aplicar una decision obsoleta.
24. Como usuario, quiero comprobar el resultado real de mi aprobacion o rechazo para saber si Hermes lo aplico o encontro un error.
25. Como usuario, quiero retomar la revision de pendientes en otra conversacion sin duplicar acciones ya resueltas.

## Implementation Decisions

### Alcance y responsabilidades

- La skill dirige la interaccion y documenta el procedimiento; un script de apoyo ejecuta inventario, evaluacion, composicion de resultados y adaptacion al flujo nativo de forma repetible.
- La regla global contiene el catalogo aprobado. No se mantendra una segunda copia editable de las preguntas en el script.
- Respetar el formato global de reglas existente: `Rule:`, `Prevents:` y `Enforce with:`. Incorporar el catalogo de forma estructurada dentro de esa convencion, sin crear un arbol paralelo de politicas.
- Alcance inicial: los perfiles explicitamente autorizados `default`, `implementer` y `reviewer`. Leer y resolver sus pendientes no autoriza modificar sus prompts, configuraciones, otras skills ni controles de permisos.
- No modificar el auxiliar generador, el curator ni el template canonico como parte de esta entrega.
- La skill TypeSafe ya fue instalada y cargada en Hermes durante la planificacion. El implementador debe usarla y verificar las referencias actuales antes de integrar el servicio.

### Solicitudes y contenido evaluado

- Hermes conserva la unica cola de pendientes. Identificar cada solicitud mediante perfil, subsistema e identificador nativo; no suponer que el identificador aislado es unico entre perfiles.
- Inventariar los archivos de memoria y perfil de usuario, asi como todas las operaciones de skills presentes en la cola nativa.
- Enviar el payload literal de operaciones propuesto, incluyendo sus campos de accion y destino disponibles. No resumirlo, corregirlo, traducirlo ni enriquecerlo con informacion de la conversacion o de otros archivos.
- La envoltura administrativa local sirve para identificar y aplicar la decision. No agregar evidencias externas al contenido enviado a Jev.
- Examinar tanto altas como sustituciones y eliminaciones. Las preguntas deben distinguir texto que se propone conservar de texto que se propone retirar: eliminar contenido malo no es proponer guardarlo.
- Los criterios solo pueden exigir informacion disponible en la solicitud. No prometer deteccion de duplicados contra toda la biblioteca, veracidad frente a una conversacion ausente ni ausencia de perdida de clausulas del destino original a partir del payload solo.

### Regla y preguntas Noul

- Cada criterio contiene identificador estable, version, pregunta, contexto pertinente, definicion de si/no, exclusiones y ejemplos cuando sean necesarios. Mantener la estructura pequena; no exigir ejemplos artificiales para llenar campos.
- La pregunta y sus datos explicativos pueden usar instrucciones estructuradas. Estos datos definen la politica; no son contexto adicional recuperado sobre la solicitud.
- Una pregunta debe medir una sola condicion coherente. Formular todas las condiciones en la misma direccion: mayor probabilidad significa mayor probabilidad de que exista el problema descrito.
- Enviar todas las preguntas independientes aplicables en una unica llamada por solicitud. Ninguna pregunta puede depender del resultado de otra en esa llamada.
- No promediar las probabilidades ni presentarlas como severidad, calidad global o autorizacion. No inventar un campo de confianza independiente ni una explicacion textual supuestamente producida por Jev.
- El agente puede interpretar los resultados durante la conversacion, distinguiendo claramente su comentario de la salida real del modelo.
- El catalogo inicial no tendra criterios sustantivos inventados: se derivaran de solicitudes reales y requeriran confirmacion del usuario. Con catalogo vacio, no llamar a Jev ni fabricar puntuaciones; mostrar `SIN CRITERIOS` y comenzar la revision humana.
- Rechazar una solicitud no agrega automaticamente una regla. Primero proponer la generalizacion y obtener consentimiento especifico.

### Evaluacion y actualizacion de resultados

- Tomar un inventario del lote al iniciar. Evaluar todos sus pendientes elegibles antes de presentarlos individualmente, respetando limites del proveedor y mostrando errores parciales sin perder el resto del lote.
- Al agregar un criterio aprobado, evaluarlo sobre todos los pendientes restantes. Si cambia una pregunta existente, invalidar y recalcular sus resultados afectados.
- Reutilizar resultados solo si coinciden el payload, el criterio con su version y la identidad del modelo evaluador. No reutilizar resultados de un alias de modelo mutable sin comprobar su identidad efectiva.
- No establecer umbrales de aprobacion automatica. Mostrar las probabilidades reales; cualquier agrupacion visual futura por umbrales necesitara una politica explicitamente aprobada.
- Fallos de red, credenciales de servicio ausentes, respuestas incompletas, datos invalidos o limites del proveedor dejan la solicitud pendiente y marcada como no evaluada o evaluacion incompleta. No convertirlos en una probabilidad cero.
- No enviar contenido truncado silenciosamente. Si una solicitud excede los limites del servicio, retenerla para revision humana e indicar el motivo.

### Seguridad previa al envio

- Aplicar una comprobacion local determinista de patrones de credenciales: formatos reconocibles de claves, bloques de claves privadas y asignaciones sospechosas de secretos.
- Un hallazgo retiene toda la solicitud para revision local; no redactarla para despues enviarla, ni enviarla a otro modelo para decidir si el secreto es real.
- No mostrar el valor sospechoso en registros ni en el panel. Indicar la categoria y retencion. Las referencias a nombres de variables o handles no deben confundirse automaticamente con el valor de una credencial.
- Declarar la limitacion: el detector puede tener falsos positivos y falsos negativos; no certifica que todo texto aprobado este libre de secretos.
- Usar las credenciales de TypeSafe mediante el mecanismo seguro disponible, sin pedirlas en el chat ni guardarlas en la regla o skill. La falta de credenciales bloquea la prueba real, no autoriza resultados simulados.

### Revision humana y ASCII

- Presentar una solicitud por turno, en espanol, con estructura visual ASCII sencilla: bordes `+`, `-` y `|`, etiquetas consistentes y columnas alineadas. No depender de colores, emojis ni caracteres de caja Unicode.
- El panel debe incluir: posicion en el lote, perfil, subsistema/destino, ID, operaciones propuestas, estado de evaluacion, modelo efectivo, version del catalogo y probabilidades por criterio.
- Mostrar el contenido propuesto literalmente en una seccion separada del panel o dentro de ella cuando quepa; el ajuste visual de lineas no puede reescribir el contenido. Para solicitudes extensas, usar bloques continuados claramente numerados y no ocultar operaciones.
- Las barras ASCII, si se usan, son una ayuda visual junto a la probabilidad numerica, nunca un reemplazo de esta. Conservar precision en el registro aunque la pantalla redondee.
- Distinguir visualmente `SIN CRITERIOS`, `RETENIDA LOCALMENTE`, `ERROR DE EVALUACION` y `EVALUADA`. Ninguno implica aprobacion.
- Ofrecer decisiones claras: aprobar, rechazar, dejar pendiente o discutir/proponer criterio. No ejecutar una decision implicita por avanzar al siguiente caso.
- Cualquier ejemplo de aspecto incluido en documentacion o pruebas debe estar rotulado como ilustrativo, no como una respuesta real de Jev.

### Integracion nativa y verificacion

- Aprobar/rechazar por solicitud completa, respetando el flujo nativo de Hermes. No dividir operaciones ni crear una implementacion propia de escritura de memoria o skills.
- Usar el mecanismo nativo bajo el perfil correcto. La integracion exacta debe comprobarse contra la instalacion: la existencia de comandos slash no demuestra por si sola que exista un subcomando shell equivalente.
- Antes de aplicar, comprobar que el pendiente sigue existiendo y coincide con lo revisado. Si cambio, detener esa accion y solicitar una nueva revision.
- Tras aprobar, verificar el resultado nativo, el destino afectado y la retirada del pendiente. Tras rechazar, verificar que el pendiente correcto desaparecio y que no se aplico su contenido.
- Un fallo al aplicar no equivale a una aprobacion. Conservar el pendiente cuando Hermes lo conserve, mostrar el error y no intentar reparar o reescribir automaticamente la solicitud.
- Conservar los avisos nativos sobre reemplazo completo de entradas. No sustituirlos por una interpretacion simplificada del agente.
- Las correcciones de propuestas requieren una nueva decision explicita; la primera version no necesita un editor de operaciones para resolver pendientes.

### Supuestos operativos para cerrar la especificacion

Estos detalles no se decidieron expresamente y se proponen como defaults de implementacion, sin ampliar autoridad:

- Invocacion sugerida: `memory-request-review`; el nombre final debe evitar colisiones con skills existentes.
- Orden de presentacion: antiguedad de la solicitud, con desempate estable por perfil, subsistema e ID.
- Los pendientes nuevos que aparezcan durante una revision se anuncian al refrescar el inventario; no se mezclan silenciosamente con el lote ya evaluado.
- Guardar localmente resultados y decisiones con identidad de solicitud, huella del payload, version de criterios y modelo para reanudacion y futuras mediciones. Este registro no es otra cola, no se sube a git y no copia conversaciones ni credenciales. No almacenar por defecto otra copia integra del payload.
- Un criterio requiere version nueva al cambiar de significado; las puntuaciones anteriores no sirven como evidencia de la version nueva.

## Testing Decisions

- Probar comportamiento observable del flujo completo, usando como seam principal la entrada de pendientes y decisiones humanas y la salida de evaluaciones, paneles y acciones nativas. Sustituir el transporte TypeSafe y el adaptador nativo en pruebas aisladas, sin mockear cada funcion interna.
- Usar perfiles y almacenes temporales de prueba, nunca aprobar/rechazar pendientes reales para obtener cobertura.
- Prior art inspeccionado: Hermes ya tiene pruebas de aprobacion de escrituras, operaciones de memoria y lotes de skills. Reutilizar sus garantias y convenciones; no duplicar su motor de aplicacion.
- Inventario: colas vacias, tres perfiles, ambos subsistemas, IDs repetidos entre perfiles, registros ilegibles y solicitudes con multiples operaciones. Comprobar conteos contra los registros realmente recogidos.
- Transporte: el payload enviado coincide semanticamente con el literal nativo, no contiene conversacion ni destinos recuperados y agrupa las preguntas aplicables. Diferenciar respuestas reales, fixtures y fallos.
- Criterios: catalogo vacio no realiza llamadas; una condicion nueva evalua solo lo que falta; cambios de payload, pregunta o modelo invalidan resultados afectados.
- Evaluacion semantica: incluir ejemplos y contraejemplos revisados por el usuario; probar una solicitud que elimina texto temporal para evitar marcarla como si lo conservara. No afirmar calidad del clasificador a partir de unicamente respuestas mockeadas.
- Seguridad: credenciales reconocibles retenidas sin trafico externo; referencias inocuas a variables; no exposicion de valores en salida o registros. Documentar casos no cubiertos por el detector.
- Aprobacion: sin autorizacion no hay acciones nativas; aprobacion y rechazo apuntan al perfil e ID correctos; solicitudes cambiadas o ya resueltas no se ejecutan; fallos permanecen visibles y no se reportan como exito.
- ASCII: pruebas de instantanea para solicitud corta, larga, varias operaciones, nombres largos, probabilidades extremas y estados sin resultados. Bordes ASCII y contenido legible sin truncado silencioso.
- Errores: servicio no disponible, limite de contexto, respuesta parcial y fallo de aplicacion. El usuario puede continuar con otros casos sin perder el estado de los no resueltos.
- Verificacion real de entrega: ejecutar al menos una consulta Jev con un criterio aprobado y una solicitud elegible autorizada, y probar la integracion nativa en un perfil aislado de prueba. Si no hay criterio o credenciales, reportar ese bloqueo y no declarar verificada la integracion real.
- La prueba de conexion demuestra que el servicio funciona; no demuestra que la politica tenga calidad suficiente para automatizar decisiones.

## Out of Scope

- Aprobacion o rechazo automaticos, incluso con probabilidades extremas.
- Procesamiento por llegada o calendario; todo se inicia bajo demanda.
- Panel web, plugin de interfaz o sustitucion de la cola nativa de Hermes.
- Cambiar permisos globales, configuracion canonica, prompts del auxiliar o politicas del curator.
- Enviar conversaciones, bibliotecas completas de skills o memorias actuales a TypeSafe.
- Editar parcialmente operaciones de un pendiente o reescribir propuestas sin autorizacion.
- Crear criterios sustantivos sin revisarlos con el usuario, entrenar modelos o calibrar umbrales de autonomia en esta primera entrega.
- Convertir el detector local de credenciales en una promesa de seguridad absoluta.
- Reabrir solicitudes ya aprobadas/rechazadas cuando se agrega un criterio.

## Further Notes

- Esta especificacion recoge la entrevista y autoriza preparar la implementacion; no afirma que la skill, la regla o el pipeline ya existan.
- No se suministro ticket Jira ni otro ticket local. Se crea un ticket padre local enlazado a esta especificacion.
- No estaban disponibles la guia local de scratch ni su plantilla global en este checkout; se aplica la convencion de respaldo de la skill `to-spec`.
- La convencion global verificada ubica las reglas bajo `agents/rules/`, no en un nuevo directorio literal `global/rule/`.
- El checkout contenia cambios ajenos al esfuerzo al comenzar esta escritura; no forman parte de la entrega y deben preservarse.
- Fuentes tecnicas consultadas: implementacion local de revision auxiliar y aprobacion de escrituras de Hermes; documentacion oficial de TypeSafe sobre Noul, instrucciones estructuradas y composicion de preguntas. Revalidar contratos al implementar.
