# 02: Definir los criterios reales que se envían a Jev

Status: pending (requiere decisión humana)
Jira: (none)
**Specification:** ../spec.md

**Blocked by:** 01 (skill de revisión implementada; ya disponible)

## Objetivo

Sustituir el criterio provisional `unclear-proposal` por preguntas reales,
derivadas de solicitudes pendientes reales, en el catálogo de la skill
(`criteria.json`). Toda edición del catálogo requiere que la persona apruebe
explícitamente el diff exacto antes de escribirlo.

## Candidatos a discutir

Surgieron de la solicitud 1 (credenciales QA del proyecto y `flutter test` en Android).
Ninguno está aprobado; cada uno debe describir un solo problema, con mayor
probabilidad = problema más probable.

- `secret-exposure`: ¿el payload contiene una credencial o indica dónde está
  guardada exactamente? (p. ej. "password vive en ~/.bashrc … linea ~165").
- `brittle-detail`: ¿depende de detalles que pronto dejarán de ser ciertos,
  como números de línea o rutas temporales?
- `wrong-scope`: ¿este conocimiento encaja mejor en los archivos de un proyecto
  que en la memoria global?
- `unverified-claim`: ¿afirma como hecho algo que la conversación no demostró
  haber comprobado?
- Descartado: `duplicates-existing` necesitaría enviar la memoria actual a Jev,
  algo que la skill prohíbe.

## Criterios de aceptación

- [ ] La persona elige qué candidatos conservar, reformular o añadir, y si se
      elimina `unclear-proposal`.
- [ ] Cada criterio aprobado tiene `id`, `version`, `question`, `context`,
      `definition.yes` y `definition.no`, más `exclusions`/`examples` solo si
      aclaran.
- [ ] El diff de `criteria.json` se muestra y se aprueba explícitamente antes
      de escribirlo; `catalog_version` se incrementa.
- [ ] Las pruebas de la skill pasan con el catálogo nuevo.
- [ ] Se vuelven a evaluar todos los pendientes restantes con los criterios
      nuevos.
