import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "panialera.db"

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS categorias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            descripcion TEXT,
            precio REAL NOT NULL,
            stock INTEGER DEFAULT 0,
            stock_minimo INTEGER DEFAULT 5,
            categoria_id INTEGER REFERENCES categorias(id),
            activo INTEGER DEFAULT 1,
            creado TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS pedidos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_nombre TEXT,
            cliente_email TEXT,
            cliente_telefono TEXT,
            cliente_direccion TEXT,
            total REAL DEFAULT 0,
            estado TEXT DEFAULT 'pendiente',
            creado TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS items_pedido (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pedido_id INTEGER REFERENCES pedidos(id),
            producto_id INTEGER REFERENCES productos(id),
            cantidad INTEGER,
            precio_unitario REAL
        );
        CREATE TABLE IF NOT EXISTS movimientos_stock (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id INTEGER REFERENCES productos(id),
            tipo TEXT,
            cantidad INTEGER,
            motivo TEXT,
            fecha TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.commit()

    # Datos demo si está vacío
    if c.execute("SELECT COUNT(*) FROM categorias").fetchone()[0] == 0:
        cats = ["Pañales", "Ropa de bebé", "Higiene", "Alimentación", "Juguetes", "Accesorios"]
        for cat in cats:
            c.execute("INSERT INTO categorias (nombre) VALUES (?)", (cat,))
        demo = [
            ("Pañales Pampers Talle M x30", "Pañales suaves con protección 12 horas", 2800, 50, 5, 1),
            ("Pañales Huggies Talle G x28", "Máxima absorción para bebés activos", 3100, 35, 5, 1),
            ("Body manga corta 0-3 meses", "100% algodón, varios colores", 1500, 20, 3, 2),
            ("Jabón líquido Johnson's bebé 200ml", "pH neutro, sin lágrimas", 950, 40, 5, 3),
            ("Crema Bepanthen 30g", "Para prevenir rozaduras", 1800, 4, 5, 3),
            ("Mamadera Avent 260ml", "Con tetina anticoliche", 2200, 15, 3, 4),
            ("Sonajero mordillo", "Libre de BPA, colores estimulantes", 1200, 30, 5, 5),
            ("Mochila portabebé ergonómica", "Para bebés de 4 a 15kg", 8500, 8, 2, 6),
        ]
        for nombre, desc, precio, stock, stock_min, cat_id in demo:
            c.execute("""INSERT INTO productos (nombre, descripcion, precio, stock, stock_minimo, categoria_id)
                         VALUES (?,?,?,?,?,?)""", (nombre, desc, precio, stock, stock_min, cat_id))
        conn.commit()
    conn.close()

# ─── Productos ────────────────────────────────────────────────────────────────

def listar_productos(solo_activos=True):
    conn = get_conn()
    q = "SELECT p.*, c.nombre as categoria FROM productos p LEFT JOIN categorias c ON p.categoria_id=c.id"
    if solo_activos:
        q += " WHERE p.activo=1"
    q += " ORDER BY p.nombre"
    rows = conn.execute(q).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def buscar_producto(nombre):
    conn = get_conn()
    rows = conn.execute(
        "SELECT p.*, c.nombre as categoria FROM productos p LEFT JOIN categorias c ON p.categoria_id=c.id "
        "WHERE p.activo=1 AND p.nombre LIKE ?", (f"%{nombre}%",)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def obtener_producto(pid):
    conn = get_conn()
    row = conn.execute(
        "SELECT p.*, c.nombre as categoria FROM productos p LEFT JOIN categorias c ON p.categoria_id=c.id WHERE p.id=?", (pid,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None

def guardar_producto(datos, pid=None):
    conn = get_conn()
    if pid:
        conn.execute("""UPDATE productos SET nombre=?, descripcion=?, precio=?, stock=?,
                        stock_minimo=?, categoria_id=?, activo=? WHERE id=?""",
                     (datos["nombre"], datos.get("descripcion",""), datos["precio"],
                      datos["stock"], datos.get("stock_minimo",5), datos.get("categoria_id"),
                      datos.get("activo",1), pid))
    else:
        conn.execute("""INSERT INTO productos (nombre, descripcion, precio, stock, stock_minimo, categoria_id)
                        VALUES (?,?,?,?,?,?)""",
                     (datos["nombre"], datos.get("descripcion",""), datos["precio"],
                      datos["stock"], datos.get("stock_minimo",5), datos.get("categoria_id")))
        pid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return pid

def ajustar_stock(producto_id, cantidad, tipo="ajuste", motivo="Manual"):
    conn = get_conn()
    conn.execute("UPDATE productos SET stock = stock + ? WHERE id=?", (cantidad, producto_id))
    conn.execute("INSERT INTO movimientos_stock (producto_id, tipo, cantidad, motivo) VALUES (?,?,?,?)",
                 (producto_id, tipo, cantidad, motivo))
    conn.commit()
    conn.close()

def productos_stock_bajo():
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM productos WHERE activo=1 AND stock <= stock_minimo ORDER BY stock ASC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ─── Categorías ───────────────────────────────────────────────────────────────

def listar_categorias():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM categorias ORDER BY nombre").fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ─── Pedidos ──────────────────────────────────────────────────────────────────

def crear_pedido(cliente, items):
    """items = [{"producto_id": x, "cantidad": y, "precio_unitario": z}, ...]"""
    conn = get_conn()
    total = sum(i["cantidad"] * i["precio_unitario"] for i in items)
    cur = conn.execute("""INSERT INTO pedidos (cliente_nombre, cliente_email, cliente_telefono, cliente_direccion, total)
                          VALUES (?,?,?,?,?)""",
                       (cliente.get("nombre"), cliente.get("email"),
                        cliente.get("telefono"), cliente.get("direccion"), total))
    pedido_id = cur.lastrowid
    for item in items:
        conn.execute("INSERT INTO items_pedido (pedido_id, producto_id, cantidad, precio_unitario) VALUES (?,?,?,?)",
                     (pedido_id, item["producto_id"], item["cantidad"], item["precio_unitario"]))
        conn.execute("UPDATE productos SET stock = stock - ? WHERE id=?", (item["cantidad"], item["producto_id"]))
        conn.execute("INSERT INTO movimientos_stock (producto_id, tipo, cantidad, motivo) VALUES (?,?,?,?)",
                     (item["producto_id"], "venta", -item["cantidad"], f"Pedido #{pedido_id}"))
    conn.commit()
    conn.close()
    return pedido_id

def listar_pedidos(estado=None, limit=50):
    conn = get_conn()
    q = "SELECT * FROM pedidos"
    params = []
    if estado:
        q += " WHERE estado=?"
        params.append(estado)
    q += " ORDER BY creado DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def obtener_pedido(pid):
    conn = get_conn()
    pedido = conn.execute("SELECT * FROM pedidos WHERE id=?", (pid,)).fetchone()
    if not pedido:
        conn.close()
        return None
    items = conn.execute("""SELECT ip.*, p.nombre FROM items_pedido ip
                             JOIN productos p ON ip.producto_id=p.id WHERE ip.pedido_id=?""", (pid,)).fetchall()
    conn.close()
    return {"pedido": dict(pedido), "items": [dict(i) for i in items]}

def cambiar_estado_pedido(pedido_id, estado):
    conn = get_conn()
    conn.execute("UPDATE pedidos SET estado=? WHERE id=?", (estado, pedido_id))
    conn.commit()
    conn.close()

# ─── Estadísticas ─────────────────────────────────────────────────────────────

def estadisticas():
    conn = get_conn()
    total_productos = conn.execute("SELECT COUNT(*) FROM productos WHERE activo=1").fetchone()[0]
    stock_bajo = conn.execute("SELECT COUNT(*) FROM productos WHERE activo=1 AND stock<=stock_minimo").fetchone()[0]
    pedidos_hoy = conn.execute("SELECT COUNT(*) FROM pedidos WHERE date(creado)=date('now')").fetchone()[0]
    ventas_hoy = conn.execute("SELECT COALESCE(SUM(total),0) FROM pedidos WHERE date(creado)=date('now') AND estado!='cancelado'").fetchone()[0]
    pedidos_pendientes = conn.execute("SELECT COUNT(*) FROM pedidos WHERE estado='pendiente'").fetchone()[0]
    ventas_mes = conn.execute("SELECT COALESCE(SUM(total),0) FROM pedidos WHERE strftime('%Y-%m',creado)=strftime('%Y-%m','now') AND estado!='cancelado'").fetchone()[0]
    conn.close()
    return {
        "total_productos": total_productos,
        "stock_bajo": stock_bajo,
        "pedidos_hoy": pedidos_hoy,
        "ventas_hoy": ventas_hoy,
        "pedidos_pendientes": pedidos_pendientes,
        "ventas_mes": ventas_mes,
    }
