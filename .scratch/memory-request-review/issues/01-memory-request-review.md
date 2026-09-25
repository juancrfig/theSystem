# Revision asistida de solicitudes de memoria con Jev

Status: ready-for-agent
Jira: (none)
**Specification:** ../spec.md

## Objetivo

Implementar una skill global invocable en una conversacion nueva que inventarie los pendientes nativos de memoria y skills de `default`, `implementer` y `reviewer`, los evalúe mediante preguntas Noul de un catalogo global aprobado y los presente uno a uno en ASCII para decision humana.

## Alcance

La especificacion enlazada es la fuente de verdad. Incluye integracion con aprobacion/rechazo nativos de Hermes, retencion local determinista de posibles credenciales, solicitudes literales sin contexto recuperado, aprendizaje humano de criterios y reevaluacion de pendientes restantes. No habilitar decisiones automaticas ni modificar el generador auxiliar o el curator.

## Criterios de aceptacion

- [ ] La skill recoge y cuenta los pendientes de los tres perfiles y ambos subsistemas sin crear otra cola.
- [ ] La regla global contiene criterios Noul estructurados, versionados y aprobados por el usuario; con catalogo vacio se revisan casos reales sin inventar puntuaciones.
- [ ] Cada solicitud elegible se envia literalmente con todas las preguntas aplicables en una llamada; sin conversaciones ni memorias adicionales.
- [ ] Los posibles secretos se retienen localmente sin exponer sus valores ni enviarlos al proveedor.
- [ ] La informacion se presenta solicitud por solicitud en un panel ASCII claro con resultados reales por criterio y estados explicitos.
- [ ] Solo una decision humana explicita activa aprobacion/rechazo nativos por solicitud completa y perfil correcto; su resultado se verifica.
- [ ] Los criterios nuevos se evaluan sobre pendientes restantes y se conservan solo resultados anteriores que sigan siendo validos.
- [ ] Errores, datos cambiados y solicitudes extensas no producen aprobaciones ni truncados silenciosos.
- [ ] Pruebas aisladas y verificacion real de Jev e integracion nativa completadas, o bloqueos de verificacion declarados expresamente.

## Estado de preparacion

Especificacion creada a partir de la entrevista. TypeSafe instalado y cargado en la sesion de planificacion. Pipeline, skill de revision y regla aun no implementados. Los supuestos operativos estan identificados en la especificacion.
