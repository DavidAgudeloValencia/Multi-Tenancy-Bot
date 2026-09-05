"""Genera los PDFs de ejemplo de la base de conocimiento (solo desarrollo).

Crea documentos FICTICIOS pero realistas en `knowledge/` para desarrollar y
probar el pipeline RAG sin esperar a tener los PDFs del negocio.

Uso:
    python -m scripts.generate_sample_kb

Cuando tengas los PDFs reales (condicionados, directorios, FAQs), colócalos en
`knowledge/` y vuelve a ingestar: `python -m scripts.ingest --reset`.
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "knowledge"

# (nombre_archivo, título, [(encabezado, [párrafos...]), ...])
KNOWLEDGE: list[tuple[str, str, list[tuple[str, list[str]]]]] = [
    (
        "guia_siniestros_auto.pdf",
        "Guía de Siniestros de Auto",
        [
            (
                "¿Qué hago si me choco?",
                [
                    "Si sufres un accidente de tránsito, mantén la calma y sigue estos pasos: "
                    "1) Verifica que tú y los ocupantes estén bien. 2) Activa las luces de "
                    "emergencia y coloca los triángulos de seguridad. 3) Toma fotos de los "
                    "vehículos, las placas y el lugar del accidente. 4) Si hay heridos, llama "
                    "inmediatamente a la línea de emergencias 123.",
                    "NO abandones el lugar del accidente y no aceptes acuerdos verbales sin "
                    "dejar constancia escrita. Reporta el siniestro dentro de las 24 horas "
                    "siguientes a la línea de siniestros 01 8000 123 456, disponible las 24 "
                    "horas los 7 días de la semana.",
                    "Para reportar el siniestro necesitarás: tu documento de identidad, la "
                    "placa del vehículo, la fecha y hora del accidente y las fotos que tomaste. "
                    "El asesor de siniestros te asignará un número de caso con el que podrás "
                    "hacer seguimiento.",
                ],
            ),
            (
                "Solicitar grúa (servicio de remolque)",
                [
                    "El servicio de grúa está disponible llamando a la línea 01 8000 456 789 "
                    "desde cualquier lugar del país. El operador te pedirá la ubicación exacta, "
                    "la placa del vehículo y el número de caso del siniestro.",
                    "El tiempo estimado de llegada de la grúa es de 45 a 90 minutos según la "
                    "zona. El servicio de remolque cubre el traslado del vehículo al taller "
                    "autorizado más cercano o al lugar que indiques dentro del municipio.",
                ],
            ),
            (
                "Robo del vehículo",
                [
                    "En caso de robo del vehículo: 1) Llama a la línea de emergencias 123 y "
                    "denuncia ante la Policía Nacional, obteniendo la copia del informe. "
                    "2) Reporta el robo a la línea de siniestros 01 8000 123 456 dentro de las "
                    "24 horas. 3) Entrega la denuncia, los documentos del vehículo y las llaves "
                    "cuando te las soliciten.",
                    "La aseguradora iniciará la investigación y te informará sobre los plazos "
                    "de respuesta según las condiciones de la póliza de todo riesgo. Guarda el "
                    "número de caso asignado para hacer seguimiento.",
                ],
            ),
        ],
    ),
    (
        "asistencia_salud.pdf",
        "Asistencias en Salud",
        [
            (
                "¿Cómo pido un médico a domicilio?",
                [
                    "Para solicitar un médico a domicilio llama a la línea de asistencias "
                    "01 8000 789 123, disponible las 24 horas. También puedes solicitarlo desde "
                    "la aplicación móvil 'Mi Salud' en la opción 'Médico a domicilio'.",
                    "El operador te pedirá tus datos personales, el motivo de la consulta y tu "
                    "dirección exacta con puntos de referencia. El tiempo estimado de llegada "
                    "del médico es de 4 a 6 horas en zona urbana y hasta 12 horas en zona rural.",
                    "El servicio de médico a domicilio está cubierto por la póliza de salud "
                    "prepagada. Recuerda tener a mano tu carné para entregarlo al profesional "
                    "cuando llegue.",
                ],
            ),
            (
                "¿Dónde descargo el carné?",
                [
                    "Puedes descargar tu carné digital desde la aplicación 'Mi Salud' en la "
                    "sección 'Mi carné', o desde el portal web www.misalud.com.co ingresando "
                    "con tu número de documento.",
                    "El carné digital es válido en todas las IPS de la red y no necesitas "
                    "imprimirlo. Si prefieres una versión física, solicítala a tu asesor y te "
                    "la enviaremos a tu domicilio en un plazo de 8 días hábiles.",
                ],
            ),
            (
                "Directorio médico",
                [
                    "Para consultar el directorio de médicos e IPS de la red, ingresa a "
                    "www.misalud.com.co/directorio o llama a la línea 01 8000 456 987. "
                    "Puedes filtrar por especialidad, ciudad y EPS.",
                    "En el directorio encontrarás los horarios de atención, direcciones y "
                    "teléfonos de cada IPS. Verifica siempre que la IPS pertenezca a la red "
                    "autorizada para que tu consulta sea cubierta sin costos adicionales.",
                ],
            ),
        ],
    ),
    (
        "preguntas_frecuentes.pdf",
        "Preguntas Frecuentes",
        [
            (
                "¿Cómo pago mi cuota?",
                [
                    "Puedes pagar tu cuota mensual por PSE desde el portal web o la aplicación "
                    "móvil, con tarjeta de crédito o débito, o mediante débito automático "
                    "autorizado desde tu cuenta bancaria.",
                    "El pago se considera efectivo el día hábil siguiente a la transacción. "
                    "Conserva siempre el comprobante. Si pagas después de la fecha límite, "
                    "aplica una penalidad del 5% sobre el valor de la cuota según las "
                    "condiciones de la póliza.",
                ],
            ),
            (
                "Necesito copia de mi póliza o certificado",
                [
                    "Puedes solicitar la copia de tu póliza o un certificado de vigencia a tu "
                    "asesor, quien lo generará en un plazo máximo de 2 días hábiles. También "
                    "puedes descargarlos desde el portal web en la sección 'Mis documentos'.",
                    "Para trámites con entidades externas (bancos, embajadas) solicita el "
                    "certificado de vigencia, que tiene validez oficial por 30 días.",
                ],
            ),
            (
                "Actualizar mis datos",
                [
                    "Para actualizar tu número de celular, correo o dirección, escríbele a tu "
                    "asesor o ingresa al portal web en la sección 'Mis datos'. Los cambios de "
                    "datos de contacto se reflejan en un plazo de 24 horas.",
                    "Si cambiaste de ciudad, domicilio o trabajo, es importante actualizar tu "
                    "información para que los avisos y facturas lleguen correctamente.",
                ],
            ),
            (
                "Renovación de la póliza",
                [
                    "Te enviaremos un aviso de renovación 30 días antes del vencimiento de tu "
                    "póliza. Para renovar, confirma el pago de la prima o autoriza el débito "
                    "automático antes de la fecha de vencimiento.",
                    "Si la póliza vence sin pago, pierde la cobertura y deberás solicitar una "
                    "nueva vinculación, que puede implicar nuevos requisitos de asegurabilidad.",
                ],
            ),
        ],
    ),
    (
        "condicionado_vida.pdf",
        "Condicionado General — Seguro de Vida",
        [
            (
                "Cobertura principal",
                [
                    "El seguro de vida cubre el fallecimiento del asegurado por cualquier "
                    "causa, con el pago de la suma asegurada a los beneficiarios designados. "
                    "La cobertura está vigente desde la fecha de inicio indicada en la póliza "
                    "siempre que la prima haya sido pagada.",
                ],
            ),
            (
                "Coberturas adicionales",
                [
                    "La póliza puede incluir coberturas adicionales como muerte accidental, "
                    "enfermedades graves (cáncer, infarto, accidente cerebrovascular) e "
                    "incapacidad total y permanente. Cada cobertura adicional tiene su propia "
                    "suma asegurada, indicada en la carátula de la póliza.",
                ],
            ),
            (
                "Exclusiones principales",
                [
                    "No están cubiertos: el suicidio durante los primeros dos años de vigencia, "
                    "la muerte causada por actos de guerra o terrorismo declarado, la "
                    "participación en actos delictivos dolosos y el consumo voluntario de "
                    "sustancias psicoactivas. Consulta la totalidad de exclusiones en el "
                    "condicionado general.",
                ],
            ),
            (
                "Beneficiarios",
                [
                    "El asegurado puede designar y cambiar beneficiarios en cualquier momento "
                    "solicitándolo por escrito. En caso de fallecimiento, los beneficiarios "
                    "deben presentar el certificado de defunción, copia de la póliza y su "
                    "documento de identidad para recibir la indemnización en un plazo máximo "
                    "de 30 días.",
                ],
            ),
        ],
    ),
]


def _build_pdf(
    target_dir: Path,
    filename: str,
    title: str,
    sections: list[tuple[str, list[str]]],
) -> None:
    """Construye un PDF sencillo con título, secciones y párrafos."""
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / filename

    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title=title,
    )

    story = [Paragraph(title, styles["Title"]), Spacer(1, 0.5 * cm)]
    for heading, paragraphs in sections:
        story.append(Paragraph(heading, styles["Heading2"]))
        story.append(Spacer(1, 0.2 * cm))
        for paragraph in paragraphs:
            story.append(Paragraph(paragraph, styles["BodyText"]))
            story.append(Spacer(1, 0.3 * cm))
        story.append(Spacer(1, 0.3 * cm))

    doc.build(story)
    print(f"Generado: {path.relative_to(Path(__file__).resolve().parent.parent)}")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Genera los PDFs de ejemplo")
    parser.add_argument(
        "--tenant",
        default=None,
        help="ID del agente (crea los PDFs en knowledge/{id}/)",
    )
    args = parser.parse_args()

    target = KNOWLEDGE_DIR
    if args.tenant:
        target = KNOWLEDGE_DIR / args.tenant

    for filename, title, sections in KNOWLEDGE:
        _build_pdf(target, filename, title, sections)

    print(f"\n{len(KNOWLEDGE)} PDF(s) de ejemplo creados en {target}/")
    if args.tenant:
        print(f"Ingesta con: python -m scripts.ingest --tenant {args.tenant} --reset")
    else:
        print("Ingesta con: python -m scripts.ingest --reset")


if __name__ == "__main__":
    main()
