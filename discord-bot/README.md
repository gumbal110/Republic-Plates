# 🚗 Bot de Placas Vehiculares — República Dominicana RP

Bot de Discord para gestión de placas vehiculares en servidores de roleplay (estilo gobierno dominicano).

---

## Características

- **Solicitud de placas** por ciudadanos con formulario de motivo
- **Aprobación/rechazo** por administradores con notificación automática al usuario (DM)
- **Generación automática** de placas únicas en formato `RD-####`
- **Base de datos SQLite** con tablas de solicitudes, placas y log de auditoría
- **Registro de logs** en canal de Discord configurable
- **Canal de notificaciones** para admins cuando llegan nuevas solicitudes
- **Permisos por rol** — configurable mediante `ADMIN_ROLE_NAME`
- **Estadísticas del sistema** en tiempo real

---

## Comandos

### Ciudadanos
| Comando | Descripción |
|---|---|
| `/solicitar_placa [motivo]` | Envía una solicitud de registro de placa |
| `/mis_placas` | Consulta tus placas activas |
| `/mis_solicitudes` | Historial de tus solicitudes |
| `/consultar_placa [placa]` | Consulta info pública de cualquier placa |

### Administradores (requieren rol configurado)
| Comando | Descripción |
|---|---|
| `/ver_solicitudes` | Lista todas las solicitudes pendientes |
| `/aprobar_solicitud [id]` | Aprueba y asigna placa automáticamente |
| `/rechazar_solicitud [id] [motivo]` | Rechaza con motivo obligatorio |
| `/revocar_placa [placa]` | Revoca una placa activa |
| `/buscar_placa [placa]` | Información completa de una placa |
| `/estadisticas` | Panel de estadísticas del sistema |

---

## Configuración (discord-bot/.env)

```env
DISCORD_TOKEN=         # Token del bot (ya configurado como Replit Secret)
ADMIN_ROLE_NAME=Gobierno  # Nombre del rol de administradores
GUILD_ID=0             # ID del servidor para sync rápido (0 = global)
LOG_CHANNEL_ID=0       # Canal para logs de acciones (0 = desactivado)
APPROVAL_CHANNEL_ID=0  # Canal para notificar nuevas solicitudes (0 = desactivado)
```

### Cómo obtener los IDs de canal/servidor
1. En Discord, activa **Modo Desarrollador**: Ajustes → Avanzado → Modo Desarrollador
2. Clic derecho sobre el servidor → **Copiar ID del servidor** (`GUILD_ID`)
3. Clic derecho sobre el canal → **Copiar ID del canal** (`LOG_CHANNEL_ID` / `APPROVAL_CHANNEL_ID`)

---

## Permisos del Bot en Discord Developer Portal

El bot necesita los siguientes permisos:
- `Send Messages` + `Embed Links` — para responder y enviar embeds
- `Read Message History` — para funcionamiento básico
- `Use Application Commands` — para slash commands
- `Send Messages in Threads` (opcional)

**Intents requeridos** (en la pestaña Bot):
- `Server Members Intent` — para notificar usuarios por DM

---

## Flujo de uso

```
Ciudadano → /solicitar_placa "Vehículo Toyota Corolla 2020"
    ↓ Notificación en APPROVAL_CHANNEL (si configurado)
Admin → /aprobar_solicitud 1
    ↓ Placa generada: RD-4821
    ↓ DM al ciudadano con su placa
    ↓ Log en LOG_CHANNEL (si configurado)
```
