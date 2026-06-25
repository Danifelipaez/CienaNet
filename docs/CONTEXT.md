# Contexto del Proyecto: CienaNet Bot

## Propósito
CienaNet Bot es el backend de CienRayas, una aplicación web móvil para pescadores artesanales de la **Ciénaga Grande de Santa Marta**, Colombia. El sistema conecta a los pescadores con información ambiental (temperatura del agua, salinidad, pH) recolectada por una red de sensores IoT de bajo costo, entregada a través de WhatsApp porque es el canal que ya usan.

## El Problema
Los pescadores artesanales de la Ciénaga no tienen acceso a datos ambientales en tiempo real que les permitan tomar mejores decisiones sobre dónde y cuándo pescar. La Ciénaga sufre de contaminación, cambios de salinidad y degradación ambiental que afectan directamente sus capturas y medios de vida.

## Usuarios Primarios
- **Pescadores artesanales** de la Ciénaga Grande de Santa Marta
- Nivel de alfabetización digital: bajo-medio
- Canal preferido: WhatsApp (no apps nativas)
- Idioma: español, algunos con influencia de lenguaje local/palafito

## Fase Actual
**MVP** — transición desde prototipo funcional. Fase 1 de desarrollo técnico.

## Componentes del Sistema

### 1. CienaNet Bot (este repositorio)
Backend FastAPI que orquesta:
- Mensajes de WhatsApp entrantes/salientes vía Meta API
- Ingesta de datos de sensores IoT
- Lógica de respuesta y alertas

### 2. Red de Sensores IoT
Sensores de bajo costo basados en **Arduino + ESP32** desplegados en la Ciénaga que miden:
- **pH** del agua
- **Conductividad eléctrica** (proxy de salinidad)
- **Temperatura** del agua

### 3. Datos Satelitales (fase futura)
NASA MODIS, Copernicus Marine, Open-Meteo para contexto ambiental ampliado.

## Equipo
| Persona | Rol | Área |
|---------|-----|------|
| Daniel | Tech Lead / PM | Ing. Sistemas |
| Valentina | Desarrollo y datos | Ing. Sistemas |
| Diego | Análisis territorial | Ing. Civil |
| Soe | Investigación comunitaria | Historia |
| Luis | Vínculo con comunidad | Etnoeducación |

## Valores No Negociables
- **Co-diseño comunitario**: las decisiones de producto se validan con pescadores
- **Pertinencia cultural**: el lenguaje y flujos de WhatsApp deben ser apropiados para el contexto
- **Bajo costo**: hardware y servicios cloud deben ser accesibles y sostenibles
- **Privacidad**: datos de los pescadores se manejan con consentimiento informado

## Gestión del Proyecto
- **Herramienta**: Microsoft Planner
- **Metodología**: Ágil (sprints cortos)
- **Historias de usuario**: formato INVEST — "Yo como [rol] quiero [acción] para [valor]"
