"""
Servidor web de chat para clientes.
Funciona tanto en local (con la app de escritorio) como en la nube (Railway/Render).
"""
from flask import Flask, render_template, request, jsonify
import anthropic
import os
import json
import socket
from pathlib import Path
import database as db

app = Flask(__name__, template_folder="templates_web", static_folder="static")
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Inicializar base de datos al arrancar (gunicorn o directo)
db.init_db()

CONFIG_PATH = Path(__file__).parent / "config.json"

def get_api_key():
    # En la nube: variable de entorno. En local: config.json
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        try:
            key = json.loads(CONFIG_PATH.read_text()).get("api_key", "")
        except Exception:
            pass
    return key

def get_ip_local():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"

def responder_cliente(pregunta: str, historial: list) -> str:
    api_key = get_api_key()
    if not api_key:
        return "En este momento no puedo responder. Contactanos por teléfono."

    productos = db.listar_productos()
    catalogo = "\n".join(
        f"- {p['nombre']}: ${p['precio']:.2f} | {'✅ Disponible' if p['stock'] > 0 else '❌ Sin stock'}"
        for p in productos
    )

    system = f"""Sos el asistente virtual de Pequeños Gigantes, una tienda de productos para bebés.
Respondés consultas de clientes de forma amable, cálida y concisa.

Catálogo actualizado:
{catalogo}

Política de la tienda:
- Envíos a todo el país
- Medios de pago: transferencia, MercadoPago, efectivo
- Los pedidos se confirman por este chat o WhatsApp
- Garantía de cambio en productos defectuosos

Reglas:
- Respondé en español, tono cordial y cercano (tuteo)
- Si preguntan por precio o disponibilidad, usá el catálogo
- Si no tenés el producto exacto, sugerí una alternativa
- Respuestas cortas y directas (máx 4 líneas)
- Si quieren hacer un pedido, pediles nombre, dirección y qué producto"""

    # El historial ya incluye el mensaje actual enviado desde el cliente
    mensajes = historial[-10:] if historial else [{"role": "user", "content": pregunta}]

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            system=system,
            messages=mensajes
        )
        return response.content[0].text
    except Exception as e:
        return "Disculpá, hubo un problema. Escribinos por WhatsApp y te respondemos enseguida 😊"


@app.after_request
def agregar_headers(response):
    response.headers["ngrok-skip-browser-warning"] = "true"
    return response

@app.route("/")
def index():
    return render_template("chat_cliente.html")

@app.route("/api/cliente/chat", methods=["POST"])
def chat_cliente():
    data = request.json
    pregunta = data.get("mensaje", "").strip()
    historial = data.get("historial", [])
    if not pregunta:
        return jsonify({"respuesta": ""})
    respuesta = responder_cliente(pregunta, historial)
    return jsonify({"respuesta": respuesta})

@app.route("/productos")
def productos_json():
    prods = db.listar_productos()
    return jsonify(prods)

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

@app.route("/api/admin/sync", methods=["POST"])
def sync_productos():
    token = request.headers.get("X-Sync-Token", "")
    if token != os.environ.get("SYNC_TOKEN", "pg-sync-2024"):
        return jsonify({"error": "no autorizado"}), 401

    data = request.json or {}
    productos = data.get("productos", [])
    categorias = data.get("categorias", [])

    conn = db.get_conn()
    try:
        # Sincronizar categorías
        for cat in categorias:
            existe = conn.execute("SELECT id FROM categorias WHERE id=?", (cat["id"],)).fetchone()
            if existe:
                conn.execute("UPDATE categorias SET nombre=? WHERE id=?", (cat["nombre"], cat["id"]))
            else:
                conn.execute("INSERT INTO categorias (id, nombre) VALUES (?,?)", (cat["id"], cat["nombre"]))

        # Sincronizar productos
        for p in productos:
            existe = conn.execute("SELECT id FROM productos WHERE id=?", (p["id"],)).fetchone()
            if existe:
                conn.execute("""UPDATE productos SET nombre=?, descripcion=?, precio=?,
                    stock=?, stock_minimo=?, categoria_id=?, activo=? WHERE id=?""",
                    (p["nombre"], p.get("descripcion",""), p["precio"],
                     p["stock"], p.get("stock_minimo",5), p.get("categoria_id"),
                     p.get("activo",1), p["id"]))
            else:
                conn.execute("""INSERT INTO productos (id, nombre, descripcion, precio,
                    stock, stock_minimo, categoria_id, activo) VALUES (?,?,?,?,?,?,?,?)""",
                    (p["id"], p["nombre"], p.get("descripcion",""), p["precio"],
                     p["stock"], p.get("stock_minimo",5), p.get("categoria_id"), p.get("activo",1)))
        conn.commit()
        return jsonify({"ok": True, "productos": len(productos)})
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


if __name__ == "__main__":
    puerto = int(os.environ.get("PORT", 5001))
    ip = get_ip_local()
    print(f"\n{'='*50}")
    print(f"  Pequeños Gigantes — Chat de clientes")
    print(f"  http://{ip}:{puerto}")
    print(f"{'='*50}\n")
    app.run(host="0.0.0.0", port=puerto, debug=False)
