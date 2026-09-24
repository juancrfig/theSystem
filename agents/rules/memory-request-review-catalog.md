# Catálogo de criterios para revisar solicitudes de memoria

Rule: Las solicitudes pendientes de memoria y skills solo pueden recibir una
aprobación o rechazo mediante una decisión humana explícita; Jev informa
probabilidades por criterio y nunca autoriza una escritura.

Prevents: Que una puntuación, una ausencia de resultados o un error de proveedor
se convierta en una decisión automática que modifique conocimiento persistente.

Enforce with: Verificar que el revisor presenta una solicitud completa, conserva
su perfil, subsistema e ID nativos, exige una decisión explícita y comprueba el
resultado del flujo nativo antes de informar éxito.

<!-- MEMORY-REQUEST-REVIEW-CATALOG
{
  "catalog_version": 1,
  "criteria": []
}
MEMORY-REQUEST-REVIEW-CATALOG -->

## Mantenimiento del catálogo

Un criterio solo se agrega después de que el usuario confirme explícitamente una
generalización derivada de un caso real. Cada objeto debe contener `id` estable,
`version` positiva, `question`, `context`, `definition` con `yes` y `no`, y solo
los campos `exclusions` o `examples` que aclaren el criterio. Toda pregunta debe
describir un único problema; una probabilidad mayor siempre significa que ese
problema es más probable. Cambiar el significado exige aumentar `version`.

El catálogo empieza deliberadamente vacío. Con él vacío se revisan casos reales
sin llamar a Jev ni inventar puntuaciones.
