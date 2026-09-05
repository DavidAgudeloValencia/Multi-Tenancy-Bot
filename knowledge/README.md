# Base de conocimiento

Coloca aquí los **PDFs reales del negocio**:

- Condicionados generales
- Manuales de asistencia
- Directorios médicos
- Preguntas frecuentes

## PDFs de ejemplo (desarrollo)

Para generar documentos ficticios y probar el pipeline sin esperar a los reales:

```bash
python -m scripts.generate_sample_kb
```

## Reingesta

Después de añadir o modificar PDFs:

```bash
python -m scripts.ingest --reset
```

> Solo se procesan archivos `*.pdf` de esta carpeta (no subcarpetas).
